"""Tests for the `SqliteStateBackend` class."""

import pytest

from plugboard.component import Component
from plugboard.state import SqliteStateBackend
from .test_state_backend import A_components  # noqa: F401


@pytest.fixture
def db_path() -> str:
    """Returns the path to the SQLite database file."""
    return "plugboard-testing.db"


@pytest.mark.anyio
async def test_state_backend_upsert_component(
    A_components: list[Component],  # noqa: F811
    db_path: str,
) -> None:
    """Tests `SqliteStateBackend.upsert_component` method."""
    state_backend = SqliteStateBackend(db_path=db_path)
    await state_backend.init()

    comp_a1, comp_a2 = A_components

    await comp_a1.init()
    await comp_a2.init()

    await state_backend.upsert_component(comp_a1)
    await state_backend.upsert_component(comp_a2)

    assert await state_backend.get_component(comp_a1.id) == comp_a1.dict()
    assert await state_backend.get_component(comp_a2.id) == comp_a2.dict()

    comp_a1_dict_prev, comp_a2_dict_prev = comp_a1.dict(), comp_a2.dict()
    for i in range(5):
        await comp_a1.step()
        state_data_a2_stale = await state_backend.get_component(comp_a1.id)
        assert state_data_a2_stale == comp_a1_dict_prev
        assert state_data_a2_stale["step_count"] == i
        await state_backend.upsert_component(comp_a1)
        state_data_a2_fresh = await state_backend.get_component(comp_a1.id)
        assert state_data_a2_fresh == comp_a1.dict()
        assert state_data_a2_fresh["step_count"] == i + 1

        await comp_a2.step()
        state_data_a2_stale = await state_backend.get_component(comp_a2.id)
        assert state_data_a2_stale == comp_a2_dict_prev
        assert state_data_a2_stale["step_count"] == i
        await state_backend.upsert_component(comp_a2)
        state_data_a2_fresh = await state_backend.get_component(comp_a2.id)
        assert state_data_a2_fresh == comp_a2.dict()
        assert state_data_a2_fresh["step_count"] == i + 1

        comp_a1_dict_prev, comp_a2_dict_prev = comp_a1.dict(), comp_a2.dict()
