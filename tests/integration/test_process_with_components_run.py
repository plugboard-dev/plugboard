"""Integration tests for running a Process with Components."""
# ruff: noqa: D101,D102,D103

from pathlib import Path
from tempfile import NamedTemporaryFile
import typing as _t

import aiofiles
import pytest

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioChannel, Connector, ConnectorSpec
from plugboard.process import Process


class ComponentTestHelper(Component):
    io = IO(inputs=[], outputs=[])

    @property
    def is_initialised(self) -> bool:
        return self._is_initialised

    @property
    def is_finished(self) -> bool:
        return self._is_finished

    @property
    def step_count(self) -> int:
        return self._step_count

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._is_initialised = False
        self._is_finished = False
        self._step_count = 0

    async def init(self) -> None:
        self._is_initialised = True

    async def step(self) -> None:
        self._step_count += 1

    async def run(self) -> None:
        await super().run()
        self._is_finished = True


class A(ComponentTestHelper):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        self.out_1 = next(self._seq)


class B(ComponentTestHelper):
    io = IO(inputs=["in_1"], outputs=["out_1"])

    def __init__(self, *args: _t.Any, factor: float = 1.0, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._factor = factor

    async def step(self) -> None:
        self.out_1 = self._factor * self.in_1  # type: ignore


class C(ComponentTestHelper):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._path = path

    async def step(self) -> None:
        out = self.in_1  # type: ignore
        async with aiofiles.open(self._path, "a") as f:
            await f.write(f"{out}\n")


@pytest.fixture
def tempfile_path() -> _t.Generator[Path, None, None]:
    with NamedTemporaryFile() as f:
        yield Path(f.name)


@pytest.mark.anyio
@pytest.mark.parameterize(
    "iters, factor",
    [
        (10, 2.0),
    ],
)
async def test_process_with_components_run(iters: int, factor: float, tempfile_path: Path) -> None:
    comp_a = A(iters=iters, name="comp_a")
    comp_b = B(factor=factor, name="comp_a")
    comp_c = C(path=str(tempfile_path), name="comp_a")
    components = [comp_a, comp_b, comp_c]

    conn_ab = Connector(
        spec=ConnectorSpec(source="comp_a.out_1", target="comp_b.in_1"), channel=AsyncioChannel()
    )
    conn_bc = Connector(
        spec=ConnectorSpec(source="comp_b.out_1", target="comp_c.in_1"), channel=AsyncioChannel()
    )
    connectors = [conn_ab, conn_bc]

    process = Process(components, connectors)

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

    with tempfile_path.open() as f:
        data = f.read()

    comp_c_outputs = [float(output) for output in data.splitlines()]
    expected_comp_c_outputs = [factor * i for i in range(iters)]
    assert comp_c_outputs == expected_comp_c_outputs
