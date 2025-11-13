"""Integration tests for the component decorator."""
# ruff: noqa: D101,D102,D103

import asyncio
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
from plugboard.connector.rabbitmq_channel import RabbitMQConnector
from plugboard.process import LocalProcess, Process, ProcessBuilder, RayProcess
from plugboard.schemas import (
    ComponentSpec,
    ConnectorBuilderArgsSpec,
    ConnectorBuilderSpec,
    ConnectorSpec,
    ProcessArgsSpec,
    ProcessSpec,
    StateBackendSpec,
    Status,
)
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
            print(f"{self.name} output: {self.a}")
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


@component(inputs=["a"], outputs=["b"])
async def comp_b_func(a: int) -> dict[str, int]:
    await asyncio.sleep(0.01)
    print(f"comp_b_func received: a={a}, outputting: {2 * a}")
    return {"b": 2 * a}


@component(inputs=["a"], outputs=["c"])
def comp_c_func(a: int) -> dict[str, int]:
    print(f"comp_c_func received: a={a}, outputting: {3 * a}")
    return {"c": 3 * a}


@component(inputs=["b", "c"], outputs=["d"])
async def comp_d_func(b: int, c: int) -> dict[str, int]:
    print(f"comp_d_func received: b={b}, c={c}, outputting: {b + c}")
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


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "process_cls, connector_cls",
    [
        (LocalProcess, AsyncioConnector),
        # (RayProcess, RayConnector),  # TODO : Pubsub/StopEvent unsupported. See https://github.com/plugboard-dev/plugboard/issues/101.
        (RayProcess, RabbitMQConnector),
    ],
)
async def test_process_builder_with_decorated_components(
    process_cls: type[Process],
    connector_cls: type[Connector],
    ray_ctx: None,
) -> None:
    """Tests a process using components created with the component decorator executes correctly."""
    iters = 10
    process_spec = ProcessSpec(
        type=f"{process_cls.__module__}.{process_cls.__name__}",
        args=ProcessArgsSpec(
            components=[
                ComponentSpec(
                    type="tests.integration.test_component_decorator.A",
                    args={"name": "comp_a", "iters": iters},
                ),
                ComponentSpec(
                    type="tests.integration.test_component_decorator.comp_b_func",
                    args={"name": "comp_b"},
                ),
                ComponentSpec(
                    type="tests.integration.test_component_decorator.comp_c_func",
                    args={"name": "comp_c"},
                ),
                ComponentSpec(
                    type="tests.integration.test_component_decorator.comp_d_func",
                    args={"name": "comp_d"},
                ),
                ComponentSpec(
                    type="tests.integration.test_component_decorator.E",
                    args={"name": "comp_e"},
                ),
            ],
            connectors=[
                ConnectorSpec(source="comp_a.a", target="comp_b.a"),
                ConnectorSpec(source="comp_a.a", target="comp_c.a"),
                ConnectorSpec(source="comp_b.b", target="comp_d.b"),
                ConnectorSpec(source="comp_c.c", target="comp_d.c"),
                ConnectorSpec(source="comp_d.d", target="comp_e.d"),
            ],
            state=StateBackendSpec(type="plugboard.state.RayStateBackend")
            if process_cls is RayProcess
            else StateBackendSpec(type="plugboard.state.DictStateBackend"),
        ),
        connector_builder=ConnectorBuilderSpec(
            type=f"{connector_cls.__module__}.{connector_cls.__name__}",
            args=ConnectorBuilderArgsSpec(),
        ),
    )

    process = ProcessBuilder.build(process_spec)
    await process.init()
    await process.run()

    assert process.status == Status.COMPLETED
    for c in process.components.values():
        assert c.status == Status.COMPLETED

    comp_e = process.components["comp_e"]
    expected_results = [5 * i for i in range(iters)]
    assert comp_e.results == expected_results

    await process.destroy()
