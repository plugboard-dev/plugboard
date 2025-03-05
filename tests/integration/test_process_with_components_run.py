"""Integration tests for running a Process with Components."""
# ruff: noqa: D101,D102,D103

from pathlib import Path
from tempfile import NamedTemporaryFile
import typing as _t

from aiofile import async_open
import pytest

from plugboard import exceptions
from plugboard.component import IOController as IO
from plugboard.connector import AsyncioConnector, Connector, RayConnector
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ConnectorSpec
from tests.conftest import ComponentTestHelper


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (RayProcess, RayConnector),
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
