"""Integration tests for `StateBackend`."""

import pytest

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioChannel, Connector
from plugboard.process import Process
from plugboard.schemas import ConnectorSpec
from plugboard.state import DictStateBackend
from tests.conftest import ComponentTestHelper


class A(ComponentTestHelper):
    """`A` component class."""

    io = IOController(inputs=["in_1", "in_2"], outputs=["out_1", "out_2"])


@pytest.fixture
def components() -> list[Component]:
    """Returns a tuple of `A` components."""
    return [A(name="A1", max_steps=5), A(name="A2", max_steps=5)]


@pytest.fixture
def connectors() -> list[Connector]:
    """Returns a tuple of connectors."""
    return [
        Connector(
            spec=ConnectorSpec(source="A1.out_1", target="A2.in_1"), channel=AsyncioChannel()
        ),
        Connector(
            spec=ConnectorSpec(source="A1.out_2", target="A2.in_2"), channel=AsyncioChannel()
        ),
    ]


@pytest.mark.asyncio
async def test_state_backend_upsert_component(components: list[Component]) -> None:
    """Tests `StateBackend` upsert component."""
    state_backend = DictStateBackend()

    comp_a1, comp_a2 = components

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
async def test_state_backend_upsert_connector(connectors: list[Connector]) -> None:
    """Tests `StateBackend` upsert connector."""
    state_backend = DictStateBackend()

    conn_1, conn_2 = connectors

    await state_backend.upsert_connector(conn_1)
    await state_backend.upsert_connector(conn_2)

    assert await state_backend.get_connector(conn_1.id) == conn_1.dict()
    assert await state_backend.get_connector(conn_2.id) == conn_2.dict()


@pytest.mark.asyncio
async def test_state_backend_upsert_process(
    components: list[Component], connectors: list[Connector]
) -> None:
    """Tests `StateBackend` upsert process."""
    state_backend = DictStateBackend()

    comp_a1, comp_a2 = components
    conn_1, conn_2 = connectors

    process_1 = Process(name="P1", components=[comp_a1, comp_a2], connectors=[conn_1, conn_2])
    await state_backend.upsert_process(process_1)

    process_2 = Process(name="P2", components=[comp_a1, comp_a2], connectors=[conn_1, conn_2])
    await state_backend.upsert_process(process_2)

    assert await state_backend.get_process(process_1.id) == process_1.dict()
    assert await state_backend.get_process(process_2.id) == process_2.dict()

    process_1.components.pop(comp_a1.id)
    await state_backend.upsert_process(process_1)
    assert await state_backend.get_process(process_1.id) == process_1.dict()


@pytest.mark.asyncio
async def test_state_backend_process_init(
    components: list[Component], connectors: list[Connector]
) -> None:
    """Tests `StateBackend` process run."""
    state_backend = DictStateBackend()

    comp_a1, comp_a2 = components
    conn_1, conn_2 = connectors

    process = Process(
        name="P1", components=[comp_a1, comp_a2], connectors=[conn_1, conn_2], state=state_backend
    )

    # Calling process init should add all components and connectors to the StateBackend.
    await process.init()

    assert await state_backend.get_process(process.id) == process.dict()
    assert await state_backend.get_component(comp_a1.id) == comp_a1.dict()
    assert await state_backend.get_component(comp_a2.id) == comp_a2.dict()
    assert await state_backend.get_connector(conn_1.id) == conn_1.dict()
    assert await state_backend.get_connector(conn_2.id) == conn_2.dict()
