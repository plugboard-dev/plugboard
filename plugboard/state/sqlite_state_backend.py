"""Provides `SqliteStateBackend` for single host persistent state handling."""

from __future__ import annotations

# from contextlib import AsyncExitStack
import typing as _t

import aiosqlite
from async_lru import alru_cache
import msgspec

from plugboard.exceptions import NotFoundError
from plugboard.state import sqlite_queries as q
from plugboard.state.state_backend import StateBackend


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class SqliteStateBackend(StateBackend):
    """`SqliteStateBackend` handles single host persistent state."""

    def __init__(self, db_path: str = "plugboard.db", *args: _t.Any, **kwargs: _t.Any) -> None:
        """Initializes `SqliteStateBackend` with `db_path`."""
        self._db_path: str = db_path
        # self._db_conn: _t.Optional[aiosqlite.Connection] = None
        # self._ctx: AsyncExitStack = AsyncExitStack()
        super().__init__(*args, **kwargs)

    # @property
    # def _db(self) -> aiosqlite.Connection:
    #     """Returns the database connection."""
    #     if self._db_conn is None:
    #         raise ValueError("Database connection not initialized.")
    #     return self._db_conn

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    async def _initialise_db(self) -> None:
        """Initializes the database."""
        # Create database with a table storing json data
        # db = await self._ctx.enter_async_context(aiosqlite.connect(self._db_path))
        # self._db_conn = db
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(q.CREATE_TABLE)
            await db.commit()

    async def init(self) -> None:
        """Initializes the `SqliteStateBackend`."""
        await self._initialise_db()
        await super().init()

    async def destroy(self) -> None:
        """Destroys the `SqliteStateBackend`."""
        # NOTE : Persistent connection causes process to hang on exit if not closed.
        # await self._ctx.aclose()
        pass

    async def upsert_process(self, process: Process, with_components: bool = False) -> None:
        """Upserts a process into the state."""
        process_data = process.dict()
        component_data = process_data.pop("components")
        connector_data = process_data.pop("connectors")
        process_json = msgspec.json.encode(process_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(q.UPSERT_PROCESS, (process_json, self.job_id))
            await db.execute(q.SET_JOB_FOR_PROCESS, (self.job_id, process.id))

            process_component_ids = []
            components_json = []
            for component_id, component in component_data.items():
                process_component_ids.append((process.id, component_id))
                if with_components:
                    component_json = msgspec.json.encode(component)
                    components_json.append((component_json, process.id))

            await db.executemany(q.SET_PROCESS_FOR_COMPONENT, process_component_ids)
            if with_components:
                await db.executemany(q.UPSERT_COMPONENT, components_json)

            process_connector_ids = []
            connectors_json = []
            for connector_id, connector in connector_data.items():
                process_connector_ids.append((process.id, connector_id))
                if with_components:
                    connector_json = msgspec.json.encode(connector)
                    connectors_json.append((connector_json, process.id))

            await db.executemany(q.SET_PROCESS_FOR_CONNECTOR, process_connector_ids)
            if with_components:
                await db.executemany(q.UPSERT_CONNECTOR, connectors_json)

            await db.commit()

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_PROCESS, (process_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process with id {process_id} not found.")
            data_json = row["data"]
            cursor = await db.execute(q.GET_COMPONENTS_FOR_PROCESS, (process_id,))
            component_rows = await cursor.fetchall()
            cursor = await db.execute(q.GET_CONNECTORS_FOR_PROCESS, (process_id,))
            connector_rows = await cursor.fetchall()
        process_data = msgspec.json.decode(data_json)
        process_components = {row["id"]: msgspec.json.decode(row["data"]) for row in component_rows}
        process_connectors = {row["id"]: msgspec.json.decode(row["data"]) for row in connector_rows}
        process_data["components"] = process_components
        process_data["connectors"] = process_connectors
        return process_data

    @alru_cache(maxsize=128)
    async def _get_process_for_component(self, component_id: str) -> str:
        """Returns the process id for a component."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_PROCESS_FOR_COMPONENT, (component_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process for component with id {component_id} not found.")
            process_id = row["process_id"]
        return process_id

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get_process_for_component(component.id)
        component_data = component.dict()
        component_json = msgspec.json.encode(component_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(q.UPSERT_COMPONENT, (component_json, process_id))
            await db.commit()

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_COMPONENT, (component_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Component with id {component_id} not found.")
            data_json = row["data"]
        component_data = msgspec.json.decode(data_json)
        return component_data

    @alru_cache(maxsize=128)
    async def _get_process_for_connector(self, connector_id: str) -> str:
        """Returns the process id for a connector."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_PROCESS_FOR_CONNECTOR, (connector_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process for connector with id {connector_id} not found.")
            process_id = row["process_id"]
        return process_id

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get_process_for_connector(connector.id)
        connector_data = connector.dict()
        connector_json = msgspec.json.encode(connector_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(q.UPSERT_CONNECTOR, (connector_json, process_id))
            await db.commit()

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_CONNECTOR, (connector_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Connector with id {connector_id} not found.")
            data_json = row["data"]
        connector_data = msgspec.json.decode(data_json)
        return connector_data
