"""Provides `SqliteStateBackend` for single host persistent state handling."""

from __future__ import annotations

from functools import cache
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

    _id_separator: str = ":"
    _null_process_id: str = "__null_process__"

    def __init__(self, db_path: str = "plugboard.db", *args: _t.Any, **kwargs: _t.Any) -> None:
        """Initializes `SqliteStateBackend` with `db_path`."""
        self._db_path: str = db_path
        super().__init__(*args, **kwargs)

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    async def _initialise_db(self) -> None:
        """Initializes the database."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(q.CREATE_TABLE)
            await db.commit()

    async def init(self) -> None:
        """Initializes the `SqliteStateBackend`."""
        await self._initialise_db()
        await super().init()

    async def destroy(self) -> None:
        """Destroys the `SqliteStateBackend`."""
        pass

    async def _fetchone(
        self, statement: str, params: _t.Tuple[_t.Any, ...]
    ) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(statement, params)
            row = await cursor.fetchone()
            return row

    async def _get_object(self, statement: str, params: _t.Tuple[_t.Any, ...]) -> dict | None:
        """Returns an object from the state."""
        row = await self._fetchone(statement, params)
        if row is None:
            return None
        data_json = row["data"]
        object_data = msgspec.json.decode(data_json)
        return object_data

    async def _execute(self, statement: str, params: _t.Tuple[_t.Any, ...]) -> None:
        """Executes a statement in the state."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(statement, params)
            await db.commit()

    @cache
    def _get_db_id(self, entity_id: str) -> str:
        """Returns the database id for a given entity id.

        The database id for an entity is the entity id prefixed with the job id.
        If the provided entity id includes the job id, it is returned as is;
        otherwise, the job id is prefixed to the entity id.
        """
        id_parts = entity_id.split(self._id_separator)
        if len(id_parts) == 1:
            return f"{self.job_id}{self._id_separator}{entity_id}"
        if len(id_parts) != 2:
            raise ValueError(f"Invalid entity id: {entity_id}")
        if id_parts[0] != self.job_id:
            raise ValueError(f"Entity id {entity_id} does not belong to job {self.job_id}")
        return entity_id

    async def _upsert_job(self, job_data: dict) -> None:
        """Upserts a job into the state."""
        job_json = msgspec.json.encode(job_data)
        await self._execute(q.UPSERT_JOB, (job_json,))

    async def _get_job(self, job_id: str) -> dict:
        """Returns a job from the state."""
        job = await self._get_object(q.GET_JOB, (job_id,))
        if job is None:
            raise NotFoundError(f"Job with id {job_id} not found.")
        return job

    async def upsert_process(self, process: Process, with_components: bool = False) -> None:
        """Upserts a process into the state."""
        process_data = process.dict()
        process_db_id = self._get_db_id(process.id)
        component_data = process_data.pop("components")
        connector_data = process_data.pop("connectors")
        process_data["components"] = {}
        process_data["connectors"] = {}
        process_json = msgspec.json.encode(process_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(q.UPSERT_PROCESS, (process_json, process_db_id, self.job_id))

            async def _upsert_children(children: dict, q_set_id: str, q_upsert_child: str) -> None:
                children_ids = []
                children_json = []
                for child_id, child in children.items():
                    child_db_id = self._get_db_id(child_id)
                    children_ids.append((process_db_id, child_db_id))
                    if with_components:
                        child_json = msgspec.json.encode(child)
                        children_json.append((child_json, child_db_id, process_db_id))
                await db.executemany(q_set_id, children_ids)
                if with_components:
                    await db.executemany(q_upsert_child, children_json)

            await _upsert_children(component_data, q.SET_PROCESS_FOR_COMPONENT, q.UPSERT_COMPONENT)
            await _upsert_children(connector_data, q.SET_PROCESS_FOR_CONNECTOR, q.UPSERT_CONNECTOR)

            await db.commit()

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        process_db_id = self._get_db_id(process_id)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(q.GET_PROCESS, (process_db_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process with id {process_db_id} not found.")
            data_json = row["data"]
            cursor = await db.execute(q.GET_COMPONENTS_FOR_PROCESS, (process_db_id,))
            component_rows = await cursor.fetchall()
            cursor = await db.execute(q.GET_CONNECTORS_FOR_PROCESS, (process_db_id,))
            connector_rows = await cursor.fetchall()
        process_data = msgspec.json.decode(data_json)
        process_components = {
            data["id"]: data for row in component_rows if (data := msgspec.json.decode(row["data"]))
        }
        process_connectors = {
            data["id"]: data for row in connector_rows if (data := msgspec.json.decode(row["data"]))
        }
        process_data["components"] = process_components
        process_data["connectors"] = process_connectors
        return process_data

    @alru_cache(maxsize=128)
    async def _get_process_id_for_component(self, component_id: str) -> str:
        """Returns the database id of the process which a component belongs to.

        If a component does not belong to any process, it is associated with a null process.
        """
        component_db_id = self._get_db_id(component_id)
        row = await self._fetchone(q.GET_PROCESS_FOR_COMPONENT, (component_db_id,))
        if row is None:
            return self._get_db_id(self._null_process_id)
        process_id = row["process_id"]
        return process_id

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_db_id = await self._get_process_id_for_component(component.id)
        component_db_id = self._get_db_id(component.id)
        component_data = component.dict()
        component_json = msgspec.json.encode(component_data)
        await self._execute(q.UPSERT_COMPONENT, (component_json, component_db_id, process_db_id))

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        component_db_id = self._get_db_id(component_id)
        component = await self._get_object(q.GET_COMPONENT, (component_db_id,))
        if component is None:
            raise NotFoundError(f"Component with id {component_id} not found.")
        return component

    @alru_cache(maxsize=128)
    async def _get_process_id_for_connector(self, connector_id: str) -> str:
        """Returns the database id of the process which a connector belongs to.

        If a connector does not belong to any process, it is associated with a null process.
        """
        connector_db_id = self._get_db_id(connector_id)
        row = await self._fetchone(q.GET_PROCESS_FOR_CONNECTOR, (connector_db_id,))
        if row is None:
            return self._get_db_id(self._null_process_id)
        process_id = row["process_id"]
        return process_id

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_db_id = await self._get_process_id_for_connector(connector.id)
        connector_db_id = self._get_db_id(connector.id)
        connector_data = connector.dict()
        connector_json = msgspec.json.encode(connector_data)
        await self._execute(q.UPSERT_CONNECTOR, (connector_json, connector_db_id, process_db_id))

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        connector_db_id = self._get_db_id(connector_id)
        connector = await self._get_object(q.GET_CONNECTOR, (connector_db_id,))
        if connector is None:
            raise NotFoundError(f"Connector with id {connector_id} not found.")
        return connector
