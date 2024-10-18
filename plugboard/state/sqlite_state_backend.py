"""Provides `SqliteStateBackend` for single host persistent state handling."""

from pathlib import Path
import sqlite3

from plugboard.state.state_backend import StateBackend


class SqliteStateBackend(StateBackend):
    """`SqliteStateBackend` handles single host persistent state."""

    def __init__(self, db_path: str = "plugboard.db") -> None:
        """Initializes `SqliteStateBackend` with `db_path`."""
        self.db_path = db_path

    async def _initialise_db(self) -> None:
        """Initializes the database."""
        # Create database with a table storing json data
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE state (
                json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                id TEXT GENERATED ALWAYS AS (json_extract(json, '$.job_id')) VIRTUAL
            );
            """
        )
        conn.commit()
        conn.close()

    async def init(self) -> None:
        """Initializes the `SqliteStateBackend`."""
        if not Path(self.db_path).exists():
            await self._initialise_db()
        await super().init()
