"""Unit tests for `Component`."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioChannel, Connector
from plugboard.schemas import ConnectorSpec


class A(Component):
    io = IO(inputs=["a", "b"], outputs=["c"])

    async def step(self) -> None:
        self.c = {"a": self.a, "b": self.b}


@pytest.mark.anyio
@pytest.mark.parametrize("initial_values", [{"a": -1, "b": -2}, {"a": -2}, {}])
async def test_component_initial_values(initial_values: dict[str, int]) -> None:
    """Tests the initial values of a `Component`."""
    component = A(name="init_values", initial_values=initial_values)
    connectors = {
        "a": Connector(
            spec=ConnectorSpec(source="none.none", target=f"init_values.a"),
            channel=AsyncioChannel(),
        ),
        "b": Connector(
            spec=ConnectorSpec(source="none.none", target=f"init_values.b"),
            channel=AsyncioChannel(),
        ),
    }
    component.io.connect(list(connectors.values()))
    await component.init()

    # Send 0 to all inputs
    for field in {"a", "b"}:
        await connectors[field].channel.send(0)
    await component.step()

    # Initial values must be set where specified
    for field in {"a", "b"}:
        assert component.c.get(field) == initial_values.get(field, 0)

    # Send 1 to all inputs
    for field in {"a", "b"}:
        await connectors[field].channel.send(1)
    await component.step()

    # Initial values must be set, should get 0, otherwise 1
    for field in {"a", "b"}:
        assert component.c.get(field) == 0 if field in initial_values else 1
