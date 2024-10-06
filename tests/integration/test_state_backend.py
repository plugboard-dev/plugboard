"""Integration tests for `StateBackend`."""

import pytest

from plugboard.component import Component, IOController
from plugboard.state import DictStateBackend


class A(Component):
    """`A` component class."""

    io = IOController()

    async def step(self) -> None:
        """Performs a step."""
        pass


@pytest.mark.asyncio
async def test_state_backend_upsert_component() -> None:
    """Tests `StateBackend` upsert component."""
    state_backend = DictStateBackend()

    comp = A(name="A")

    await state_backend.upsert_component(comp)
    assert await state_backend.get_component(comp.id) == comp.dict()
