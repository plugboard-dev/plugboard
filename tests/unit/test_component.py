"""Unit tests for `Component`."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.schemas import ComponentArgsDict, ConnectorSpec, Status


class A(Component):
    io = IO(inputs=["a", "b"], outputs=["c"])

    async def step(self) -> None:
        self.c = {"a": self.a, "b": self.b}


class S(Component):
    io = IO(inputs=[], outputs=["component_status"])

    def __init__(self, max_iters: int = 5, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._remaining_iters = max_iters
        self.raise_exception = False

    async def step(self) -> None:
        self._remaining_iters -= 1
        if self.raise_exception:
            raise ValueError("This is a test exception.")
        self.component_status = str(self.status)
        if self._remaining_iters <= 0:
            await self.io.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_values", [{"a": [-1], "b": [-2]}, {"a": [-2]}, {"a": [-2, -1]}, {}]
)
async def test_component_initial_values(initial_values: dict[str, _t.Iterable]) -> None:
    """Tests the initial values of a `Component`."""
    component = A(name="init_values", initial_values=initial_values)
    connectors = {
        "a": AsyncioConnector(spec=ConnectorSpec(source="none.none", target=f"init_values.a")),
        "b": AsyncioConnector(spec=ConnectorSpec(source="none.none", target=f"init_values.b")),
    }
    await component.io.connect(list(connectors.values()))
    await component.init()

    n_init = {field: len(list(initial_values.get(field, []))) for field in {"a", "b"}}

    send_channels = {field: await connectors[field].connect_send() for field in ("a", "b")}

    for input_idx in range(5):
        # Send input_idx to all inputs
        for field in {"a", "b"}:
            await send_channels[field].send(input_idx)
        await component.step()

        # Initial values must be set where specified
        for field in {"a", "b"}:
            if n_init[field] >= input_idx + 1:
                assert component.c.get(field) == list(initial_values[field])[input_idx]
            else:
                assert component.c.get(field) == input_idx - n_init[field]

    await component.io.close()


@pytest.mark.asyncio
async def test_component_status() -> None:
    """Tests the status of a `Component` across its lifecycle."""
    component = S(name="status-component")
    assert component.status == Status.CREATED, "Component should start with CREATED status"

    await component.init()
    assert component.status == Status.INIT, "Component should be INIT after init"

    component.raise_exception = False
    await component.step()
    assert component.status == Status.WAITING, "Component should be WAITING after step"
    assert component.component_status == "running", "Status should be running during step"

    component.raise_exception = True
    try:
        await component.step()
    except ValueError:
        pass
    assert component.status == Status.FAILED, "Component should be FAILED after exception"

    run_component = S(name="run-status-component")
    await run_component.init()

    run_component.raise_exception = False
    await run_component.run()
    assert run_component.status == Status.COMPLETED, "Component should be COMPLETED after run"
