"""Tests for the `SqliteStateBackend` class."""

import asyncio
import multiprocessing as mp
from multiprocessing.managers import SyncManager

import inject
import pytest

from plugboard.component import Component, IOController
from plugboard.connector import Connector, ZMQChannel
from plugboard.process import Process
from plugboard.schemas.connector import ConnectorSpec
from plugboard.state import SqliteStateBackend
from tests.conftest import ComponentTestHelper


class A(ComponentTestHelper):
    """`A` component class with no input or output fields."""

    io = IOController(outputs=["out_1", "out_2"])


class B(ComponentTestHelper):
    """`B` component class with input and output fields."""

    io = IOController(inputs=["in_1", "in_2"])


@pytest.fixture
def components() -> list[Component]:
    """Returns a tuple of components."""
    return [
        A(name="A1", max_steps=5),
        A(name="A2", max_steps=5),
        B(name="B1", max_steps=5),
        B(name="B2", max_steps=5),
    ]


@pytest.fixture
def connectors() -> list[Connector]:
    """Returns a tuple of connectors."""
    manager = inject.instance(SyncManager)
    return [
        Connector(
            spec=ConnectorSpec(source="A1.out_1", target="B1.in_1"),
            channel=ZMQChannel(manager=manager),
        ),
        Connector(
            spec=ConnectorSpec(source="A1.out_2", target="B1.in_2"),
            channel=ZMQChannel(manager=manager),
        ),
        Connector(
            spec=ConnectorSpec(source="A2.out_1", target="B2.in_1"),
            channel=ZMQChannel(manager=manager),
        ),
        Connector(
            spec=ConnectorSpec(source="A2.out_2", target="B2.in_2"),
            channel=ZMQChannel(manager=manager),
        ),
    ]


@pytest.fixture
def db_path() -> str:
    """Returns the path to the SQLite database file."""
    return "plugboard-testing.db"


# @pytest.mark.anyio
# async def test_state_backend_upsert_component(
#     A_components: list[Component],  # noqa: F811
#     db_path: str,
# ) -> None:
#     """Tests `SqliteStateBackend.upsert_component` method."""
#     state_backend = SqliteStateBackend(db_path=db_path)
#     await state_backend.init()

#     comp_a1, comp_a2 = A_components

#     await comp_a1.init()
#     await comp_a2.init()

#     await state_backend.upsert_component(comp_a1)
#     await state_backend.upsert_component(comp_a2)

#     assert await state_backend.get_component(comp_a1.id) == comp_a1.dict()
#     assert await state_backend.get_component(comp_a2.id) == comp_a2.dict()

#     comp_a1_dict_prev, comp_a2_dict_prev = comp_a1.dict(), comp_a2.dict()
#     for i in range(5):
#         await comp_a1.step()
#         state_data_a2_stale = await state_backend.get_component(comp_a1.id)
#         assert state_data_a2_stale == comp_a1_dict_prev
#         assert state_data_a2_stale["step_count"] == i
#         await state_backend.upsert_component(comp_a1)
#         state_data_a2_fresh = await state_backend.get_component(comp_a1.id)
#         assert state_data_a2_fresh == comp_a1.dict()
#         assert state_data_a2_fresh["step_count"] == i + 1

#         await comp_a2.step()
#         state_data_a2_stale = await state_backend.get_component(comp_a2.id)
#         assert state_data_a2_stale == comp_a2_dict_prev
#         assert state_data_a2_stale["step_count"] == i
#         await state_backend.upsert_component(comp_a2)
#         state_data_a2_fresh = await state_backend.get_component(comp_a2.id)
#         assert state_data_a2_fresh == comp_a2.dict()
#         assert state_data_a2_fresh["step_count"] == i + 1

#         comp_a1_dict_prev, comp_a2_dict_prev = comp_a1.dict(), comp_a2.dict()


@pytest.mark.asyncio
async def test_state_backend_multiprocess(
    components: list[Component],  # noqa: F811
    connectors: list[Connector],  # noqa: F811
    db_path: str,
) -> None:
    """Tests `StateBackend.upsert_process` method."""
    state_backend = SqliteStateBackend(db_path=db_path)

    comp_a1, comp_a2, comp_b1, comp_b2 = components
    conn_1, conn_2, conn_3, conn_4 = connectors

    process_1 = Process(name="P1", components=[comp_a1, comp_b1], connectors=[conn_1, conn_2])
    process_2 = Process(name="P2", components=[comp_a2, comp_b2], connectors=[conn_3, conn_4])

    await process_1.connect_state(state=state_backend)
    await process_2.connect_state(state=state_backend)

    assert await state_backend.get_process(process_1.id) == process_1.dict()
    assert await state_backend.get_process(process_2.id) == process_2.dict()

    state_data_comp_a1 = await state_backend.get_component(comp_a1.id)
    state_data_comp_b1 = await state_backend.get_component(comp_b1.id)
    state_data_comp_a2 = await state_backend.get_component(comp_a2.id)
    state_data_comp_b2 = await state_backend.get_component(comp_b2.id)
    assert state_data_comp_a1["is_initialised"] is False
    assert state_data_comp_b1["is_initialised"] is False
    assert state_data_comp_a2["is_initialised"] is False
    assert state_data_comp_b2["is_initialised"] is False

    # Run components in separate processes with multiprocessing
    mp_processes = []

    def init_component(comp: Component) -> None:
        async def _inner() -> None:
            await comp.init()
            print("Component initialised.")

        asyncio.run(_inner())

    for comp in [*process_1.components.values(), *process_2.components.values()]:
        p = mp.Process(target=init_component, args=(comp,))
        mp_processes.append(p)
        p.start()

    for p in mp_processes:
        p.join()

    state_data_comp_a1 = await state_backend.get_component(comp_a1.id)
    state_data_comp_b1 = await state_backend.get_component(comp_b1.id)
    state_data_comp_a2 = await state_backend.get_component(comp_a2.id)
    state_data_comp_b2 = await state_backend.get_component(comp_b2.id)
    assert state_data_comp_a1["is_initialised"] is True
    assert state_data_comp_b1["is_initialised"] is True
    assert state_data_comp_a2["is_initialised"] is True
    assert state_data_comp_b2["is_initialised"] is True
