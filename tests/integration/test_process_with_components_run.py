"""Integration tests for running a Process with Components."""
# ruff: noqa: D101,D102,D103

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile
import typing as _t
from unittest import mock

from aiofile import async_open
import pytest
import pytest_cases

from plugboard import exceptions
from plugboard.component import IOController as IO
from plugboard.component.component import IO_READ_TIMEOUT_SECONDS
from plugboard.connector import AsyncioConnector, Connector, RabbitMQConnector, RayConnector
from plugboard.exceptions import ProcessStatusError
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ConnectorSpec
from plugboard.schemas.state import Status
from tests.conftest import ComponentTestHelper, zmq_connector_cls


class A(ComponentTestHelper):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


class B(ComponentTestHelper):
    io = IO(inputs=["in_1"], outputs=["out_1"])

    def __init__(self, *args: _t.Any, factor: float = 1.0, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._factor = factor

    async def step(self) -> None:
        self.out_1 = self._factor * self.in_1
        await super().step()


class C(ComponentTestHelper):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._path = path

    async def step(self) -> None:
        out = self.in_1
        async with async_open(self._path, "a") as f:
            await f.write(f"{out}\n")
        await super().step()


@pytest.fixture
def tempfile_path() -> _t.Generator[Path, None, None]:
    with NamedTemporaryFile() as f:
        yield Path(f.name)


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (LocalProcess, zmq_connector_cls),
        (LocalProcess, RabbitMQConnector),
        (RayProcess, RayConnector),
        (RayProcess, zmq_connector_cls),
        (RayProcess, RabbitMQConnector),
    ],
)
@pytest.mark.parametrize(
    "iters, factor",
    [
        (1, 1.0),
        (10, 2.0),
    ],
)
async def test_process_with_components_run(
    process_cls: type[Process],
    connector_cls: type[Connector],
    iters: int,
    factor: float,
    tempfile_path: Path,
    ray_ctx: None,
) -> None:
    comp_a = A(iters=iters, name="comp_a")
    comp_b = B(factor=factor, name="comp_b")
    comp_c = C(path=str(tempfile_path), name="comp_c")
    components = [comp_a, comp_b, comp_c]

    conn_ab = connector_cls(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b.in_1"))
    conn_bc = connector_cls(spec=ConnectorSpec(source="comp_b.out_1", target="comp_c.in_1"))
    connectors = [conn_ab, conn_bc]

    process = process_cls(components, connectors)

    # Running before initialisation should raise an error
    with pytest.raises(exceptions.NotInitialisedError):
        await process.run()

    await process.init()
    for c in components:
        assert c.is_initialised

    await process.step()
    for c in components:
        assert c.step_count == 1

    await process.run()
    for c in components:
        assert c.is_finished
        assert c.step_count == iters

    assert comp_a.out_1 == iters - 1
    assert comp_c.in_1 == (iters - 1) * factor

    with tempfile_path.open() as f:
        data = f.read()

    comp_c_outputs = [float(output) for output in data.splitlines()]
    expected_comp_c_outputs = [factor * i for i in range(iters)]
    assert comp_c_outputs == expected_comp_c_outputs


class SlowProducer(ComponentTestHelper):
    """Component that produces data slowly, with delays longer than IO timeout."""

    io = IO(outputs=["out_1"])

    def __init__(self, delay: float, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._delay = delay
        self._iters = iters

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        # Delay before producing output to simulate slow data arrival
        await asyncio.sleep(self._delay)
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


class SlowConsumer(ComponentTestHelper):
    """Component that consumes data and should handle process failure gracefully."""

    io = IO(inputs=["in_1"])

    async def step(self) -> None:
        # Just consume the input
        _ = self.in_1
        await super().step()


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (RayProcess, RayConnector),
    ],
)
async def test_io_read_with_slow_data_arrival(
    process_cls: type[Process], connector_cls: type[Connector]
) -> None:
    """Test that IO read succeeds when data arrives slowly (longer than timeout)."""
    # Use a delay longer than the IO_READ_TIMEOUT_SECONDS (set via env var for this test)
    delay = IO_READ_TIMEOUT_SECONDS + 2.0

    slow_producer = SlowProducer(delay=delay, iters=2, name="slow_producer")
    consumer = SlowConsumer(name="consumer")

    connector = connector_cls(
        spec=ConnectorSpec(source="slow_producer.out_1", target="consumer.in_1")
    )

    process = process_cls(
        components=[slow_producer, consumer], connectors=[connector], name="slow_data_process"
    )

    await process.init()

    # Patch the function in the component module where it's actually called
    with (
        mock.patch.object(
            process.state, "get_process_status_for_component", return_value=Status.RUNNING
        ) as mock_get_status,
    ):
        # First step should succeed despite the delay
        start_time = asyncio.get_event_loop().time()
        await process.step()
        end_time = asyncio.get_event_loop().time()

        # Verify the step took at least the delay time
        assert end_time - start_time >= delay
        assert slow_producer.step_count == 1
        assert consumer.step_count == 1

        # Verify that the process status was checked during the timeout
        mock_get_status.assert_called_once_with(consumer.id)

    await process.destroy()


class FailingComponent(ComponentTestHelper):
    """Component that fails after a specified number of steps."""

    io = IO(inputs=["in_1"], outputs=["out_1"])

    def __init__(self, fail_after: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._fail_after = fail_after

    async def step(self) -> None:
        if self.step_count >= self._fail_after:
            # Trigger failure by raising an exception
            raise RuntimeError(f"Component {self.name} failed after {self._fail_after} steps")
        self.out_1 = self.in_1
        await super().step()


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (RayProcess, RayConnector),
    ],
)
async def test_io_read_with_process_failure(
    process_cls: type[Process], connector_cls: type[Connector]
) -> None:
    """Test that ProcessStatusError is raised when process status is failed."""
    producer = A(iters=5, name="producer")
    failing_comp = FailingComponent(fail_after=2, name="failing_comp")
    consumer = SlowConsumer(name="consumer")

    conn1 = connector_cls(spec=ConnectorSpec(source="producer.out_1", target="failing_comp.in_1"))
    conn2 = connector_cls(spec=ConnectorSpec(source="failing_comp.out_1", target="consumer.in_1"))

    process = process_cls(
        components=[producer, failing_comp, consumer],
        connectors=[conn1, conn2],
        name="failing_process",
    )

    await process.init()

    # First step should succeed
    await process.step()
    assert producer.step_count == 1
    assert failing_comp.step_count == 1
    assert consumer.step_count == 1

    # Second step should succeed
    await process.step()
    assert producer.step_count == 2
    assert failing_comp.step_count == 2
    assert consumer.step_count == 2

    # Third step should cause failing_comp to fail
    with pytest.raises(ExceptionGroup) as exc_info:
        await process.step()

    # Verify that we have the expected exceptions
    exceptions = exc_info.value.exceptions

    if process_cls == RayProcess:
        # For Ray, we expect both the component failure and the process status error
        assert len(exceptions) == 2
        underlying_errors = []
        for e in exceptions:
            if hasattr(e, "cause") and e.cause:
                underlying_errors.append(type(e.cause))
        assert RuntimeError in underlying_errors
        assert ProcessStatusError in underlying_errors
    else:
        # For LocalProcess, we only expect the component failure initially
        assert len(exceptions) == 1
        inner_exception = exceptions[0]
        assert isinstance(inner_exception, RuntimeError)
        assert "Component failing_comp failed after 2 steps" in str(inner_exception)

    # Verify the failing component status is FAILED
    assert failing_comp.status == Status.FAILED

    # The process status should be updated to FAILED due to the failing component
    process_status = await process.state.get_process_status(process.id)
    assert process_status == Status.FAILED

    # For LocalProcess, manually test the consumer behavior
    if process_cls == LocalProcess:
        # TODO : Change logic of process run to prevent cancellation (similar to Ray)?
        # # Consumer should now raise ProcessStatusError when trying to read
        # with pytest.raises(
        #     ProcessStatusError, match="Process in failed state for component consumer"
        # ):
        # # Verify consumer status is now STOPPED
        # assert consumer.status == Status.STOPPED

        with pytest.raises(asyncio.CancelledError):
            await consumer.step()
        assert consumer.status == Status.RUNNING

    await process.destroy()
