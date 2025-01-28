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
@pytest.mark.parametrize(
    "initial_values", [{"a": [-1], "b": [-2]}, {"a": [-2]}, {"a": [-2, -1]}, {}]
)
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

    n_init = {field: len(initial_values.get(field, [])) for field in {"a", "b"}}

    for input_idx in range(5):
        # Send input_idx to all inputs
        for field in {"a", "b"}:
            await connectors[field].channel.send(input_idx)
        await component.step()

        # Initial values must be set where specified
        for field in {"a", "b"}:
            if n_init[field] >= input_idx + 1:
                assert component.c.get(field) == initial_values[field][input_idx]
            else:
                assert component.c.get(field) == input_idx - n_init[field]
