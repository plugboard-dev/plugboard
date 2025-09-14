"""Tests for the `StateBackend` classes that permit multiprocessing."""

import typing as _t

import pytest
import pytest_asyncio
from ray.util.multiprocessing import Pool
import uvloop

from plugboard.component import Component, IOController
from plugboard.connector import Connector, ZMQConnector
from plugboard.process import LocalProcess
from plugboard.schemas.connector import ConnectorSpec
from plugboard.state import DictStateBackend, StateBackend
from tests.conftest import ComponentTestHelper
from tests.integration.conftest import (
    setup_PostgresStateBackend,
    setup_RayStateBackend,
    setup_SqliteStateBackend,
)


class A(ComponentTestHelper):
    """`A` component class with no input or output fields."""

    io = IOController(outputs=["out_1", "out_2"])

    async def step(self) -> None:  # noqa: D102
        pass


class B(ComponentTestHelper):
    """`B` component class with input and output fields."""

    io = IOController(inputs=["in_1", "in_2"])

    async def step(self) -> None:  # noqa: D102
        pass


@pytest.fixture
def components() -> list[Component]:
    """Returns a list of components."""
    return [
        A(name="A1", max_steps=5),
        A(name="A2", max_steps=5),
        B(name="B1", max_steps=5),
        B(name="B2", max_steps=5),
    ]


class ConnectorTestHelper(ZMQConnector):
    """`ConnectorTestHelper` tracks and outputs more data for storing in the state."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.times_upserted: int = 0

    def dict(self) -> dict:  # noqa: D102
        output = super().dict()
        output["times_upserted"] = self.times_upserted
        return output


@pytest_asyncio.fixture
async def connectors() -> list[Connector]:
    """Returns a list of connectors."""
    return [
        ConnectorTestHelper(spec=ConnectorSpec(source="A1.out_1", target="B1.in_1")),
        ConnectorTestHelper(spec=ConnectorSpec(source="A1.out_2", target="B1.in_2")),
        ConnectorTestHelper(spec=ConnectorSpec(source="A2.out_1", target="B2.in_1")),
        ConnectorTestHelper(spec=ConnectorSpec(source="A2.out_2", target="B2.in_2")),
    ]


@pytest_asyncio.fixture(
    params=[setup_SqliteStateBackend, setup_PostgresStateBackend, setup_RayStateBackend]
)
async def state_backend(request: pytest.FixtureRequest) -> _t.AsyncIterator[StateBackend]:
    """Returns a `StateBackend` instance."""
    state_backend_setup = request.param
    with state_backend_setup() as state_backend:
        _upsert_connector = state_backend.upsert_connector

        async def upsert_connector(connector: Connector) -> None:
            """Upserts a connector into the state."""
            if not isinstance(connector, ConnectorTestHelper):
                raise RuntimeError("`Connector` must be an instance of `ConnectorTestHelper`.")
            connector.times_upserted += 1
            await _upsert_connector(connector)

        setattr(state_backend, "upsert_connector", upsert_connector)
        yield state_backend


@pytest.mark.asyncio
async def test_state_backend_multiprocess(
    state_backend: StateBackend,  # noqa: F811
    components: list[Component],  # noqa: F811
    connectors: list[Connector],  # noqa: F811
    ray_ctx: None,
) -> None:
    """Tests `StateBackend.upsert_process` method."""
    comp_a1, comp_a2, comp_b1, comp_b2 = components
    conn_1, conn_2, conn_3, conn_4 = connectors

    for c in [conn_1, conn_2, conn_3, conn_4]:
        assert c.dict()["times_upserted"] == 0

    if isinstance(state_backend, DictStateBackend):
        # Non-persistent state backend only supports one process
        processes = [
            LocalProcess(
                name="P1",
                components=[comp_a1, comp_b1, comp_a2, comp_b2],
                connectors=[conn_1, conn_2, conn_3, conn_4],
            )
        ]

    else:
        processes = [
            LocalProcess(name="P1", components=[comp_a1, comp_b1], connectors=[conn_1, conn_2]),
            LocalProcess(name="P2", components=[comp_a2, comp_b2], connectors=[conn_3, conn_4]),
        ]

    for proc in processes:
        await proc.connect_state(state=state_backend)

    for proc in processes:
        assert await state_backend.get_process(proc.id) == proc.dict()

    # Check state data is as expected for components after connecting processes to state
    for comp in [comp_a1, comp_a2, comp_b1, comp_b2]:
        state_data_comp = await state_backend.get_component(comp.id)
        assert state_data_comp["is_initialised"] is False

    # Check state data is as expected for connectors after connecting processes to state
    for conn in [conn_1, conn_2, conn_3, conn_4]:
        state_data_conn = await state_backend.get_connector(conn.id)
        assert state_data_conn["times_upserted"] == 1

    # Run components in separate processes with multiprocessing
    def init_component(comp: Component) -> None:
        async def _inner() -> None:
            await comp.init()
            print("Component initialised.")

        uvloop.run(_inner())

    # At the end of `Component.init` the component upserts itself into the state
    # backend, so we expect the state backend to have up to date component data afterwards
    mp_processes = []
    with Pool(2) as pool:
        for comp in [c for proc in processes for c in proc.components.values()]:
            p = pool.apply_async(init_component, args=(comp,))
            mp_processes.append(p)
        for p in mp_processes:
            p.get()

    # Check state data is as expected for components after component init in child os processes
    for comp in [comp_a1, comp_a2, comp_b1, comp_b2]:
        state_data_comp = await state_backend.get_component(comp.id)
        assert state_data_comp["is_initialised"] is True

    # Run connector upsert in separate process with multiprocessing
    def upsert_connector(conn: Connector) -> None:
        async def _inner() -> None:
            await state_backend.upsert_connector(conn)

        uvloop.run(_inner())

    mp_processes = []
    with Pool(2) as pool:
        for conn in [c for proc in processes for c in proc.connectors.values()]:
            p = pool.apply_async(upsert_connector, args=(conn,))
            mp_processes.append(p)
        for p in mp_processes:
            p.get()

    # Check state data is as expected for connectors after upsert in child os processes
    for conn in [conn_1, conn_2, conn_3, conn_4]:
        state_data_conn = await state_backend.get_connector(conn.id)
        assert state_data_conn["times_upserted"] == 2
