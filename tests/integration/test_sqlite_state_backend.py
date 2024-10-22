"""Tests for the `SqliteStateBackend` class."""

import asyncio
import multiprocessing as mp

import pytest

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.process import Process
from plugboard.state import SqliteStateBackend
from .test_state_backend import A_components, B_components, B_connectors  # noqa: F401


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


@pytest.mark.asyncio
async def test_state_backend_multiprocess(
    B_components: list[Component],  # noqa: F811
    B_connectors: list[Connector],  # noqa: F811
    db_path: str,
) -> None:
    """Tests `StateBackend.upsert_process` method."""
    state_backend = SqliteStateBackend(db_path=db_path)

    comp_b1, comp_b2 = B_components
    conn_1, conn_2 = B_connectors

    process_1 = Process(name="P1", components=[comp_b1, comp_b2], connectors=[conn_1, conn_2])
    # process_2 = Process(name="P2", components=[comp_b1, comp_b2], connectors=[conn_1, conn_2])

    await process_1.connect_state(state=state_backend)

    assert await state_backend.get_process(process_1.id) == process_1.dict()
    # assert await state_backend.get_process(process_2.id) == process_2.dict()

    state_data_comp_b1 = await state_backend.get_component(comp_b1.id)
    state_data_comp_b2 = await state_backend.get_component(comp_b2.id)
    assert state_data_comp_b1["is_initialised"] is False
    assert state_data_comp_b2["is_initialised"] is False

    # Run components in separate processes with multiprocessing
    mp_processes = []

    for comp in process_1.components.values():
        p = mp.Process(target=comp.init)
        mp_processes.append(p)
        p.start()

    for p in mp_processes:
        p.join()

    state_data_comp_b1 = await state_backend.get_component(comp_b1.id)
    state_data_comp_b2 = await state_backend.get_component(comp_b2.id)
    assert state_data_comp_b1["is_initialised"] is True
    assert state_data_comp_b2["is_initialised"] is True

    def step_and_update_state(comp: Component) -> None:
        async def _inner() -> None:
            await comp.step()
            if comp.state is None:
                raise ValueError("Component state is unset.")
            await comp.state.upsert_component(comp)

        asyncio.run(_inner())

    mp_processes = []

    for comp in process_1.components.values():
        p = mp.Process(target=step_and_update_state, args=(comp,))
        mp_processes.append(p)
        p.start()

    for p in mp_processes:
        p.join()

    state_data_comp_b1 = await state_backend.get_component(comp_b1.id)
    state_data_comp_b2 = await state_backend.get_component(comp_b2.id)
    assert state_data_comp_b1["step_count"] == 1
    assert state_data_comp_b2["step_count"] == 1
