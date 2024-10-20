"""Provides `SqliteStateBackend` for single host persistent state handling."""

import typing as _t

from pathlib import Path
from textwrap import dedent

import aiosqlite
import orjson

from plugboard.state.state_backend import StateBackend

if _t.TYPE_CHECKING:
    from plugboard.component import Component


STATE_CREATE_TABLE_SQL: str = dedent(
    """\
    CREATE TABLE job (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.job_id')) VIRTUAL UNIQUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ttl INTEGER DEFAULT NULL,
        metadata TEXT GENERATED ALWAYS AS (json_extract(data, '$.metadata')) VIRTUAL,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
    );
    CREATE TABLE process (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
    );
    CREATE TABLE component (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
    );
    CREATE TABLE connector (
        data TEXT,
        id TEXT GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
    );
    """
)

STATE_UPSERT_COMPONENT: str = dedent(
    """INSERT OR REPLACE INTO component (data) VALUES (?);"""
)

STATE_GET_COMPONENT: str = dedent(
    """SELECT data FROM component WHERE id = ?;"""
)


class SqliteStateBackend(StateBackend):
    """`SqliteStateBackend` handles single host persistent state."""

    def __init__(self, db_path: str = "plugboard.db") -> None:
        """Initializes `SqliteStateBackend` with `db_path`."""
        self.db_path = db_path

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        """Returns a value from the state."""
        pass

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:
        """Sets a value in the state."""
        pass

    async def _initialise_db(self) -> None:
        """Initializes the database."""
        # Create database with a table storing json data
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(STATE_CREATE_TABLE_SQL)
            await db.commit()

    async def init(self) -> None:
        """Initializes the `SqliteStateBackend`."""
        if not Path(self.db_path).exists():
            await self._initialise_db()
        await super().init()

    async def upsert_component(self, component: Component) -> None:
        data = component.dict()
        json = orjson.dumps(data)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(STATE_UPSERT_COMPONENT, (json,))
            await db.commit()

    async def get_component(self, component_id) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(STATE_GET_COMPONENT)
            row = await cursor.fetchone()
            data = row["data"]
        component = orjson.loads(data)
        return component
        