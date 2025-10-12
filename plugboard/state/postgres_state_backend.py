"""Provides `PostgresStateBackend` for multi-host persistent state handling."""

from __future__ import annotations

import typing as _t

from async_lru import alru_cache
import asyncpg
import msgspec

from plugboard.exceptions import NotFoundError
from plugboard.schemas.state import Status
from plugboard.state import postgres_queries as q
from plugboard.state.state_backend import StateBackend


if _t.TYPE_CHECKING:  # pragma: no cover
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


class PostgresStateBackend(StateBackend):
    """`PostgresStateBackend` handles multi-host persistent state using PostgreSQL."""

    def __init__(
        self,
        db_url: str = "postgresql://plugboard:plugboard@localhost:5432/plugboard",
        *args: _t.Any,
        **kwargs: _t.Any,
    ) -> None:
        """Initializes `PostgresStateBackend` with `db_url`."""
        self._db_url: str = db_url
        self._pool: asyncpg.Pool | None = None
        super().__init__(*args, **kwargs)

    def __getstate__(self) -> dict:
        state = super().__getstate__()
        del state["_pool"]
        return state

    def __setstate__(self, state: dict) -> None:
        super().__setstate__(state)
        self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._db_url)
        if self._pool is None:
            raise ConnectionError("Could not create connection pool")
        return self._pool

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    async def _initialise_db(self) -> None:
        """Initializes the database."""
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(q.CREATE_TABLE)

    async def init(self) -> None:
        """Initializes the `PostgresStateBackend`."""
        await self._initialise_db()
        await super().init()

    async def destroy(self) -> None:
        """Destroys the `PostgresStateBackend`."""
        await super().destroy()
        if self._pool:
            await self._pool.close()
        self._get_db_id.cache_clear()
        self._get_process_id_for_component.cache_clear()
        self._get_process_id_for_connector.cache_clear()

    async def _fetchone(
        self, statement: str, params: _t.Tuple[_t.Any, ...]
    ) -> asyncpg.Record | None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            return await connection.fetchrow(statement, *params)

    async def _get_object(self, statement: str, params: _t.Tuple[_t.Any, ...]) -> dict | None:
        """Returns an object from the state."""
        row = await self._fetchone(statement, params)
        if row is None:
            return None
        object_data = msgspec.json.decode(row["data"])
        return object_data

    async def _execute(self, statement: str, params: _t.Tuple[_t.Any, ...]) -> None:
        """Executes a statement in the state."""
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            await connection.execute(statement, *params)

    async def _upsert_job(self, job_data: dict) -> None:
        """Upserts a job into the state."""
        job_id = job_data["job_id"]
        await self._execute(q.UPSERT_JOB, (job_id, msgspec.json.encode(job_data).decode()))

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
        process_data["components"] = {k: {} for k in component_data.keys()}
        process_data["connectors"] = {k: {} for k in connector_data.keys()}

        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    q.UPSERT_PROCESS,
                    process_db_id,
                    msgspec.json.encode(process_data).decode(),
                    self.job_id,
                )
                for component in component_data.values():
                    component_db_id = self._get_db_id(component["id"])
                    await connection.execute(
                        q.UPSERT_COMPONENT,
                        component_db_id,
                        msgspec.json.encode(component).decode() if with_components else "{}",
                        process_db_id,
                    )
                    await connection.execute(
                        q.SET_PROCESS_FOR_COMPONENT, process_db_id, component_db_id
                    )
                for connector in connector_data.values():
                    connector_db_id = self._get_db_id(connector["id"])
                    await connection.execute(
                        q.UPSERT_CONNECTOR,
                        connector_db_id,
                        msgspec.json.encode(connector).decode() if with_components else "{}",
                        process_db_id,
                    )
                    await connection.execute(
                        q.SET_PROCESS_FOR_CONNECTOR, process_db_id, connector_db_id
                    )

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        process_db_id = self._get_db_id(process_id)
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            process_row = await connection.fetchrow(q.GET_PROCESS, process_db_id)
            if not process_row:
                raise NotFoundError(f"Process with id {process_id} not found.")
            process_data = msgspec.json.decode(process_row["data"])

            component_rows = await connection.fetch(q.GET_COMPONENTS_FOR_PROCESS, process_db_id)
            connector_rows = await connection.fetch(q.GET_CONNECTORS_FOR_PROCESS, process_db_id)

        process_components = {
            self._strip_job_id(row["id"]): msgspec.json.decode(row["data"])
            for row in component_rows
        }
        process_connectors = {
            self._strip_job_id(row["id"]): msgspec.json.decode(row["data"])
            for row in connector_rows
        }
        process_data["components"] = process_components
        process_data["connectors"] = process_connectors
        return process_data

    async def get_process_for_component(self, component_id: str) -> dict:
        """Gets the process that a component belongs to."""
        process_id: str = await self._get_process_id_for_component(component_id)
        return await self.get_process(process_id)

    @alru_cache(maxsize=128)
    async def _get_process_id_for_component(self, component_id: str) -> str:
        component_db_id = self._get_db_id(component_id)
        row = await self._fetchone(q.GET_PROCESS_FOR_COMPONENT, (component_db_id,))
        if row is None or row["process_id"] is None:
            raise NotFoundError(f"No process found for component with ID {component_id}")
        return row["process_id"]

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get_process_id_for_component(component.id)
        process_db_id = self._get_db_id(process_id)
        component_db_id = self._get_db_id(component.id)
        component_data = component.dict()
        await self._execute(
            q.UPSERT_COMPONENT,
            (component_db_id, msgspec.json.encode(component_data).decode(), process_db_id),
        )
        if component.status in {Status.FAILED}:
            # If the component is terminal, update the process status
            await self.update_process_status(process_id, component.status)

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        component_db_id = self._get_db_id(component_id)
        component = await self._get_object(q.GET_COMPONENT, (component_db_id,))
        if component is None:
            raise NotFoundError(f"Component with id {component_id} not found.")
        return component

    @alru_cache(maxsize=128)
    async def _get_process_id_for_connector(self, connector_id: str) -> str:
        """Returns the process id for a connector."""
        connector_db_id = self._get_db_id(connector_id)
        row = await self._fetchone(q.GET_PROCESS_FOR_CONNECTOR, (connector_db_id,))
        if row is None or row["process_id"] is None:
            raise NotFoundError(f"No process found for connector with ID {connector_id}")
        return row["process_id"]

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get_process_id_for_connector(connector.id)
        process_db_id = self._get_db_id(process_id)
        connector_db_id = self._get_db_id(connector.id)
        connector_data = connector.dict()
        await self._execute(
            q.UPSERT_CONNECTOR,
            (connector_db_id, msgspec.json.encode(connector_data).decode(), process_db_id),
        )

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        connector_db_id = self._get_db_id(connector_id)
        connector = await self._get_object(q.GET_CONNECTOR, (connector_db_id,))
        if connector is None:
            raise NotFoundError(f"Connector with id {connector_id} not found.")
        return connector

    async def _update_process_status(self, process_db_id: str, status: Status) -> None:
        await self._execute(q.UPDATE_PROCESS_STATUS, (f'"{status.value}"', process_db_id))

    async def update_process_status(self, process_id: str, status: Status) -> None:
        """Updates the status of a process."""
        process_db_id = self._get_db_id(process_id)
        await self._update_process_status(process_db_id, status)

    async def get_process_status(self, process_id: str) -> Status:
        """Returns the status of a process."""
        process_db_id = self._get_db_id(process_id)
        row = await self._fetchone(q.GET_PROCESS_STATUS, (process_db_id,))
        if row is None or row["status"] is None:
            raise NotFoundError(f"Status for process {process_id} not found.")
        return Status(row["status"])

    async def get_process_status_for_component(self, component_id: str) -> Status:
        """Returns the status of a process for a given component."""
        component_db_id = self._get_db_id(component_id)
        row = await self._fetchone(q.GET_PROCESS_STATUS_FOR_COMPONENT, (component_db_id,))
        if row is None or row["status"] is None:
            raise NotFoundError(f"Status for component {component_id} not found.")
        return Status(row["status"])
