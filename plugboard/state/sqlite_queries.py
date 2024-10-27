"""SQLite queries for the state module."""

from textwrap import dedent


STATE_CREATE_TABLE_SQL: str = dedent(
    """\
    CREATE TABLE IF NOT EXISTS job (
        data TEXT,
        id TEXT NOT NULL GENERATED ALWAYS AS (json_extract(data, '$.job_id')) VIRTUAL UNIQUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ttl INTEGER DEFAULT NULL,
        metadata TEXT GENERATED ALWAYS AS (json_extract(data, '$.metadata')) VIRTUAL,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL
    );
    CREATE TABLE IF NOT EXISTS process (
        data TEXT,
        id TEXT NOT NULL GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        job_id TEXT,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS component (
        data TEXT,
        id TEXT NOT NULL GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connector (
        data TEXT,
        id TEXT NOT NULL GENERATED ALWAYS AS (json_extract(data, '$.id')) VIRTUAL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS job_process (
        job_id TEXT NOT NULL,
        process_id TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_component (
        process_id TEXT NOT NULL,
        component_id TEXT NOT NULL,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE,
        FOREIGN KEY (component_id) REFERENCES component(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_connector (
        process_id TEXT NOT NULL,
        connector_id TEXT NOT NULL,
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

STATE_GET_COMPONENTS_FOR_PROCESS_SQL: str = dedent(
    """
    SELECT id, data FROM component WHERE id IN (
        SELECT component_id FROM process_component WHERE process_id = ?
    );
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

STATE_GET_CONNECTORS_FOR_PROCESS_SQL: str = dedent(
    """
    SELECT id, data FROM connector WHERE id IN (
        SELECT connector_id FROM process_connector WHERE process_id = ?
    );
    """
)
