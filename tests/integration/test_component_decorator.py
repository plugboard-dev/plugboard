"""Integration tests for the component decorator."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest
import pytest_cases

from plugboard.component import IOController as IO
from plugboard.component.utils import component
from plugboard.connector import (
    AsyncioConnector,
    Connector,
    RayConnector,
)
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ConnectorSpec
from plugboard.schemas.state import Status
from tests.conftest import ComponentTestHelper


class A(ComponentTestHelper):
    io = IO(outputs=["a"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.a = next(self._seq)
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


@component(inputs=["a"], outputs=["b"])
async def comp_b_func(a: int) -> dict[str, int]:
    return {"b": 2 * a}


@component(inputs=["a"], outputs=["c"])
async def comp_c_func(a: int) -> dict[str, int]:
    return {"c": 3 * a}


@component(inputs=["b", "c"], outputs=["d"])
async def comp_d_func(b: int, c: int) -> dict[str, int]:
    return {"d": b + c}


class E(ComponentTestHelper):
    io = IO(inputs=["d"])
    exports = ["results"]

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.results: list[int] = []

    async def step(self) -> None:
        self.results.append(self.d)
        await super().step()


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        (RayProcess, RayConnector),
    ],
)
async def test_process_with_decorated_components(
    process_cls: type[Process],
    connector_cls: type[Connector],
    ray_ctx: None,
) -> None:
    """Tests a process using components created with the component decorator executes correctly."""
    iters = 10
    comp_a = A(iters=iters, name="comp_a")
    comp_b = comp_b_func.component(name="comp_b")
    comp_c = comp_c_func.component(name="comp_c")
    comp_d = comp_d_func.component(name="comp_d")
    comp_e = E(name="comp_e")
    components = [comp_a, comp_b, comp_c, comp_d, comp_e]

    connectors = [
        connector_cls(spec=ConnectorSpec(source="comp_a.a", target="comp_b.a")),
        connector_cls(spec=ConnectorSpec(source="comp_a.a", target="comp_c.a")),
        connector_cls(spec=ConnectorSpec(source="comp_b.b", target="comp_d.b")),
        connector_cls(spec=ConnectorSpec(source="comp_c.c", target="comp_d.c")),
        connector_cls(spec=ConnectorSpec(source="comp_d.d", target="comp_e.d")),
    ]

    process = process_cls(components, connectors)
    await process.init()
    await process.run()

    assert process.status == Status.COMPLETED
    for c in components:
        assert c.status == Status.COMPLETED

    expected_results = [5 * i for i in range(iters)]
    assert comp_e.results == expected_results

    await process.destroy()
