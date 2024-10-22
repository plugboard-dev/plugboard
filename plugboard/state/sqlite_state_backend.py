"""Provides `SqliteStateBackend` for single host persistent state handling."""

from __future__ import annotations

# from contextlib import AsyncExitStack
from textwrap import dedent
import typing as _t

import aiosqlite
from async_lru import alru_cache
import orjson

from plugboard.exceptions import NotFoundError
from plugboard.state.state_backend import StateBackend


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import Connector
    from plugboard.process import Process


STATE_CREATE_TABLE_SQL: str = dedent(
    """\
    CREATE TABLE IF NOT EXISTS job (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.job_id')) VIRTUAL UNIQUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ttl INTEGER DEFAULT NULL,
        metadata TEXT GENERATED ALWAYS AS (json_extract(data, '$.metadata')) VIRTUAL,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL
    );
    CREATE TABLE IF NOT EXISTS process (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        job_id TEXT,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS component (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connector (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS job_process (
        job_id TEXT,
        process_id TEXT,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_component (
        process_id TEXT,
        component_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE,
        FOREIGN KEY (component_id) REFERENCES component(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_connector (
        process_id TEXT,
        connector_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE,
        FOREIGN KEY (connector_id) REFERENCES connector(id) ON DELETE CASCADE
    );
    """
)

STATE_UPSERT_PROCESS_SQL: str = dedent(
    """\
    INSERT OR REPLACE INTO process (data, job_id) VALUES (?, ?);
    """
)

STATE_GET_PROCESS_SQL: str = dedent(
    """\
    SELECT data FROM process WHERE id = ?;
    """
)

STATE_SET_JOB_FOR_PROCESS_SQL: str = dedent(
    """\
    INSERT INTO job_process (job_id, process_id) VALUES (?, ?);
    """
)

STATE_GET_JOB_FOR_PROCESS_SQL: str = dedent(
    """\
    SELECT job_id FROM job_process WHERE process_id = ?;
    """
)

STATE_UPSERT_COMPONENT_SQL: str = dedent(
    """\
    INSERT OR REPLACE INTO component (data, process_id) VALUES (?, ?);
    """
)

STATE_GET_COMPONENT_SQL: str = dedent(
    """\
    SELECT data FROM component WHERE id = ?;
    """
)

STATE_SET_PROCESS_FOR_COMPONENT_SQL: str = dedent(
    """\
    INSERT INTO process_component (process_id, component_id) VALUES (?, ?);
    """
)

STATE_GET_PROCESS_FOR_COMPONENT_SQL: str = dedent(
    """\
    SELECT process_id FROM process_component WHERE component_id = ?;
    """
)

STATE_UPSERT_CONNECTOR_SQL: str = dedent(
    """\
    INSERT OR REPLACE INTO connector (data, process_id) VALUES (?, ?);
    """
)

STATE_GET_CONNECTOR_SQL: str = dedent(
    """\
    SELECT data FROM connector WHERE id = ?;
    """
)

STATE_SET_PROCESS_FOR_CONNECTOR_SQL: str = dedent(
    """\
    INSERT INTO process_connector (process_id, connector_id) VALUES (?, ?);
    """
)

STATE_GET_PROCESS_FOR_CONNECTOR_SQL: str = dedent(
    """\
    SELECT process_id FROM process_connector WHERE connector_id = ?;
    """
)


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
            await db.executescript(STATE_CREATE_TABLE_SQL)
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
        # TODO : What to do about export data? Problematic due to unserialised python objects.
        process_data.pop("__export")
        component_data = process_data.pop("components")
        connector_data = process_data.pop("connectors")
        process_json = orjson.dumps(process_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(STATE_UPSERT_PROCESS_SQL, (process_json, self.job_id))
            await db.execute(STATE_SET_JOB_FOR_PROCESS_SQL, (self.job_id, process.id))
            for component_id, component in component_data.items():
                await db.execute(STATE_SET_PROCESS_FOR_COMPONENT_SQL, (process.id, component_id))
                if with_components:
                    # TODO : What to do about export data? Problematic due to unserialised python objects.  # noqa: E501,W505
                    component.pop("__export")
                    component_json = orjson.dumps(component)
                    await db.execute(STATE_UPSERT_COMPONENT_SQL, (component_json, process.id))
            for connector_id, connector in connector_data.items():
                await db.execute(STATE_SET_PROCESS_FOR_CONNECTOR_SQL, (process.id, connector_id))
                if with_components:
                    # TODO : What to do about export data? Problematic due to unserialised python objects.  # noqa: E501,W505
                    connector.pop("__export")
                    connector_json = orjson.dumps(connector)
                    await db.execute(STATE_UPSERT_CONNECTOR_SQL, (connector_json, process.id))
            await db.commit()

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(STATE_GET_PROCESS_SQL, (process_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process with id {process_id} not found.")
            data_json = row["data"]
        process_data = orjson.loads(data_json)
        return process_data

    @alru_cache(maxsize=128)
    async def _get_process_for_component(self, component_id: str) -> str:
        """Returns the process id for a component."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(STATE_GET_PROCESS_FOR_COMPONENT_SQL, (component_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process for component with id {component_id} not found.")
            process_id = row["process_id"]
        return process_id

    async def upsert_component(self, component: Component) -> None:
        """Upserts a component into the state."""
        process_id = await self._get_process_for_component(component.id)
        component_data = component.dict()
        # TODO : What to do about export data? Problematic due to unserialised python objects.
        component_data.pop("__export")
        component_json = orjson.dumps(component_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(STATE_UPSERT_COMPONENT_SQL, (component_json, process_id))
            await db.commit()

    async def get_component(self, component_id: str) -> dict:
        """Returns a component from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(STATE_GET_COMPONENT_SQL, (component_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Component with id {component_id} not found.")
            data_json = row["data"]
        component_data = orjson.loads(data_json)
        return component_data

    @alru_cache(maxsize=128)
    async def _get_process_for_connector(self, connector_id: str) -> str:
        """Returns the process id for a connector."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(STATE_GET_PROCESS_FOR_CONNECTOR_SQL, (connector_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Process for connector with id {connector_id} not found.")
            process_id = row["process_id"]
        return process_id

    async def upsert_connector(self, connector: Connector) -> None:
        """Upserts a connector into the state."""
        process_id = await self._get_process_for_connector(connector.id)
        connector_data = connector.dict()
        # TODO : What to do about export data? Problematic due to unserialised python objects.
        connector_data.pop("__export")
        connector_json = orjson.dumps(connector_data)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(STATE_UPSERT_CONNECTOR_SQL, (connector_json, process_id))
            await db.commit()

    async def get_connector(self, connector_id: str) -> dict:
        """Returns a connector from the state."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(STATE_GET_CONNECTOR_SQL, (connector_id,))
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(f"Connector with id {connector_id} not found.")
            data_json = row["data"]
        connector_data = orjson.loads(data_json)
        return connector_data
