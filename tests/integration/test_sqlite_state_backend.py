"""Tests for the `SqliteStateBackend` class."""

import asyncio
import multiprocessing as mp
from multiprocessing.managers import SyncManager
from tempfile import NamedTemporaryFile
import typing as _t

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
    """Returns a list of components."""
    return [
        A(name="A1", max_steps=5),
        A(name="A2", max_steps=5),
        B(name="B1", max_steps=5),
        B(name="B2", max_steps=5),
    ]


class ConnectorTestHelper(Connector):
    """`ConnectorTestHelper` tracks and outputs more data for storing in the state."""

    def __init__(self, spec: ConnectorSpec, channel: ZMQChannel) -> None:
        super().__init__(spec=spec, channel=channel)
        self.times_upserted: int = 0

    def dict(self) -> dict:  # noqa: D102
        output = super().dict()
        output["times_upserted"] = self.times_upserted
        return output


class SqliteStateBackendTestHelper(SqliteStateBackend):
    """`SqliteStateBackendTestHelper` overrides methods to assist test assertions."""

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        if not isinstance(connector, ConnectorTestHelper):
            raise RuntimeError("`Connector` must be an instance of `ConnectorTestHelper`.")
        connector.times_upserted += 1
        await super().upsert_connector(connector)


@pytest.fixture
def connectors() -> list[Connector]:
    """Returns a list of connectors."""
    manager = inject.instance(SyncManager)
    return [
        ConnectorTestHelper(
            spec=ConnectorSpec(source="A1.out_1", target="B1.in_1"),
            channel=ZMQChannel(manager=manager),
        ),
        ConnectorTestHelper(
            spec=ConnectorSpec(source="A1.out_2", target="B1.in_2"),
            channel=ZMQChannel(manager=manager),
        ),
        ConnectorTestHelper(
            spec=ConnectorSpec(source="A2.out_1", target="B2.in_1"),
            channel=ZMQChannel(manager=manager),
        ),
        ConnectorTestHelper(
            spec=ConnectorSpec(source="A2.out_2", target="B2.in_2"),
            channel=ZMQChannel(manager=manager),
        ),
    ]


@pytest.fixture
def db_path() -> _t.Iterator[str]:
    """Returns the path to the SQLite database file."""
    with NamedTemporaryFile() as file:
        yield file.name


@pytest.mark.asyncio
async def test_state_backend_multiprocess(
    components: list[Component],  # noqa: F811
    connectors: list[Connector],  # noqa: F811
    db_path: str,
) -> None:
    """Tests `StateBackend.upsert_process` method."""
    state_backend = SqliteStateBackendTestHelper(db_path=db_path)

    comp_a1, comp_a2, comp_b1, comp_b2 = components
    conn_1, conn_2, conn_3, conn_4 = connectors

    for c in [conn_1, conn_2, conn_3, conn_4]:
        assert c.dict()["times_upserted"] == 0

    process_1 = Process(name="P1", components=[comp_a1, comp_b1], connectors=[conn_1, conn_2])
    process_2 = Process(name="P2", components=[comp_a2, comp_b2], connectors=[conn_3, conn_4])

    await process_1.connect_state(state=state_backend)
    await process_2.connect_state(state=state_backend)

    assert await state_backend.get_process(process_1.id) == process_1.dict()
    assert await state_backend.get_process(process_2.id) == process_2.dict()

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

        asyncio.run(_inner())

    # At the end of `Component.init` the component upserts itself into the state
    # backend, so we expect the state backend to have up to date component data afterwards
    mp_processes = []
    for comp in [*process_1.components.values(), *process_2.components.values()]:
        p = mp.Process(target=init_component, args=(comp,))
        mp_processes.append(p)
        p.start()
    for p in mp_processes:
        p.join()

    # Check state data is as expected for components after component init in child os processes
    for comp in [comp_a1, comp_a2, comp_b1, comp_b2]:
        state_data_comp = await state_backend.get_component(comp.id)
        assert state_data_comp["is_initialised"] is True

    # Run connector upsert in separate process with multiprocessing
    def upsert_connector(conn: Connector) -> None:
        async def _inner() -> None:
            await state_backend.upsert_connector(conn)

        asyncio.run(_inner())

    mp_processes = []
    for conn in [*process_1.connectors.values(), *process_2.connectors.values()]:
        p = mp.Process(target=upsert_connector, args=(conn,))
        mp_processes.append(p)
        p.start()
    for p in mp_processes:
        p.join()

    # Check state data is as expected for connectors after upsert in child os processes
    for conn in [conn_1, conn_2, conn_3, conn_4]:
        state_data_conn = await state_backend.get_connector(conn.id)
        assert state_data_conn["times_upserted"] == 2
