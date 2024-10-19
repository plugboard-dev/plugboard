"""Provides `SqliteStateBackend` for single host persistent state handling."""

from pathlib import Path
from textwrap import dedent

import aiosqlite

from plugboard.state.state_backend import StateBackend


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


class SqliteStateBackend(StateBackend):
    """`SqliteStateBackend` handles single host persistent state."""

    def __init__(self, db_path: str = "plugboard.db") -> None:
        """Initializes `SqliteStateBackend` with `db_path`."""
        self.db_path = db_path

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
