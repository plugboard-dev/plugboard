"""Integration tests for `StateBackend`."""

import typing as _t

import pytest

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioConnector, Connector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from plugboard.state import StateBackend
from tests.conftest import ComponentTestHelper
from tests.integration.conftest import (
    setup_DictStateBackend,
    setup_RayStateBackend,
    setup_SqliteStateBackend,
)


class A(ComponentTestHelper):
    """`A` component class with no input or output fields."""

    io = IOController(outputs=["out_1"])

    async def step(self) -> None:  # noqa: D102
        await super().step()


class B(ComponentTestHelper):
    """`B` component class with input and output fields."""

    io = IOController(inputs=["in_1", "in_2"], outputs=["out_1", "out_2"])

    async def step(self) -> None:  # noqa: D102
        await super().step()


class C(ComponentTestHelper):
    """`C` component class with input and output fields."""

    io = IOController(inputs=["in_1", "in_2"], outputs=["out_1", "out_2"])

    async def step(self) -> None:  # noqa: D102
        await super().step()


@pytest.fixture
def A_components() -> list[Component]:
    """Returns a tuple of `A` components."""
    return [A(name="A1", max_steps=5), A(name="A2", max_steps=5)]


@pytest.fixture
def B_components() -> list[Component]:
    """Returns a tuple of `B` components."""
    return [B(name="B1", max_steps=5), B(name="B2", max_steps=5)]


@pytest.fixture
def B_connectors() -> list[Connector]:
    """Returns a tuple of connectors for `B` components."""
    return [
        AsyncioConnector(spec=ConnectorSpec(source="B1.out_1", target="B2.in_1")),
        AsyncioConnector(spec=ConnectorSpec(source="B1.out_2", target="B2.in_2")),
    ]


@pytest.fixture
def C_components() -> list[Component]:
    """Returns a tuple of `C` components."""
    return [C(name="C1", max_steps=5), C(name="C2", max_steps=5)]


@pytest.fixture
def C_connectors() -> list[Connector]:
    """Returns a tuple of connectors for `C` components."""
    return [
        AsyncioConnector(spec=ConnectorSpec(source="C1.out_1", target="C2.in_1")),
        AsyncioConnector(spec=ConnectorSpec(source="C1.out_2", target="C2.in_2")),
    ]


@pytest.fixture(
    params=[
        setup_DictStateBackend,
        setup_SqliteStateBackend,
        setup_RayStateBackend,
    ]
)
async def state_backend(request: pytest.FixtureRequest) -> _t.AsyncIterator[StateBackend]:
    """Returns a `StateBackend` instance."""
    state_backend_setup = request.param
    with state_backend_setup() as state_backend:
        yield state_backend


@pytest.mark.asyncio
async def test_state_backend_upsert_component(
    state_backend: StateBackend, A_components: list[Component]
) -> None:
    """Tests `StateBackend.upsert_component` method."""
    comp_a1, comp_a2 = A_components

    async with state_backend:
        await state_backend.upsert_component(comp_a1)
        await state_backend.upsert_component(comp_a2)

        assert await state_backend.get_component(comp_a1.id) == comp_a1.dict()
        assert await state_backend.get_component(comp_a2.id) == comp_a2.dict()

        comp_a1_dict_prev, comp_a2_dict_prev = comp_a1.dict(), comp_a2.dict()
        for i in range(5):
            await comp_a1.step()
            state_data_a1_stale = await state_backend.get_component(comp_a1.id)
            assert state_data_a1_stale == comp_a1_dict_prev
            assert state_data_a1_stale["step_count"] == i
            await state_backend.upsert_component(comp_a1)
            state_data_a1_fresh = await state_backend.get_component(comp_a1.id)
            assert state_data_a1_fresh == comp_a1.dict()
            assert state_data_a1_fresh["step_count"] == i + 1

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
async def test_state_backend_upsert_connector(
    state_backend: StateBackend, B_connectors: list[Connector]
) -> None:
    """Tests `StateBackend.upsert_connector` method."""
    conn_1, conn_2 = B_connectors

    async with state_backend:
        await state_backend.upsert_connector(conn_1)
        await state_backend.upsert_connector(conn_2)

        assert await state_backend.get_connector(conn_1.id) == conn_1.dict()
        assert await state_backend.get_connector(conn_2.id) == conn_2.dict()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_components", [True, False])
async def test_state_backend_upsert_process(
    state_backend: StateBackend,
    B_components: list[Component],
    B_connectors: list[Connector],
    C_components: list[Component],
    C_connectors: list[Connector],
    with_components: bool,
) -> None:
    """Tests `StateBackend.upsert_process` method."""
    comp_b1, comp_b2 = B_components
    conn_1, conn_2 = B_connectors

    comp_c1, comp_c2 = C_components
    conn_3, conn_4 = C_connectors

    async with state_backend:
        process_1 = LocalProcess(
            name="P1", components=[comp_b1, comp_b2], connectors=[conn_1, conn_2]
        )
        await state_backend.upsert_process(process_1, with_components=with_components)

        process_2 = LocalProcess(
            name="P2", components=[comp_c1, comp_c2], connectors=[conn_3, conn_4]
        )
        await state_backend.upsert_process(process_2, with_components=with_components)

        process_1_dict = process_1.dict()
        process_2_dict = process_2.dict()
        if not with_components:
            process_1_dict["components"] = {}
            process_1_dict["connectors"] = {}
            process_2_dict["components"] = {}
            process_2_dict["connectors"] = {}

        assert await state_backend.get_process(process_1.id) == process_1_dict
        assert await state_backend.get_process(process_2.id) == process_2_dict


@pytest.mark.asyncio
async def test_state_backend_process_init(
    state_backend: StateBackend, B_components: list[Component], B_connectors: list[Connector]
) -> None:
    """Tests `StateBackend` connected up correctly on `Process.init`."""
    comp_b1, comp_b2 = B_components
    conn_1, conn_2 = B_connectors

    process = LocalProcess(
        name="P1", components=[comp_b1, comp_b2], connectors=[conn_1, conn_2], state=state_backend
    )

    # Calling process init should add all components and connectors to the StateBackend.
    await process.init()

    assert await state_backend.get_process(process.id) == process.dict()
    assert await state_backend.get_component(comp_b1.id) == comp_b1.dict()
    assert await state_backend.get_component(comp_b2.id) == comp_b2.dict()
    assert await state_backend.get_connector(conn_1.id) == conn_1.dict()
    assert await state_backend.get_connector(conn_2.id) == conn_2.dict()

    await process.destroy()
