"""SQLite queries for the state module."""

from textwrap import dedent


CREATE_TABLE: str = dedent(
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
        id TEXT NOT NULL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        job_id TEXT,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS component (
        data TEXT,
        id TEXT NOT NULL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connector (
        data TEXT,
        id TEXT NOT NULL UNIQUE,
        status TEXT GENERATED ALWAYS AS (json_extract(data, '$.status')) VIRTUAL,
        process_id TEXT,
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

UPSERT_JOB: str = dedent(
    """\
    INSERT OR REPLACE INTO job (data) VALUES (?);
    """
)

GET_JOB: str = dedent(
    """\
    SELECT data FROM job WHERE id = ?;
    """
)

UPSERT_PROCESS: str = dedent(
    """\
    INSERT OR REPLACE INTO process (data, id, job_id) VALUES (?, ?, ?);
    """
)

GET_PROCESS: str = dedent(
    """\
    SELECT data FROM process WHERE id = ?;
    """
)

UPSERT_COMPONENT: str = dedent(
    """\
    INSERT OR REPLACE INTO component (data, id, process_id) VALUES (?, ?, ?);
    """
)

GET_COMPONENT: str = dedent(
    """\
    SELECT data FROM component WHERE id = ?;
    """
)

SET_PROCESS_FOR_COMPONENT: str = dedent(
    """\
    INSERT INTO process_component (process_id, component_id) VALUES (?, ?);
    """
)

GET_PROCESS_FOR_COMPONENT: str = dedent(
    """\
    SELECT process_id FROM process_component WHERE component_id = ?;
    """
)

GET_COMPONENTS_FOR_PROCESS: str = dedent(
    """\
    SELECT id, data FROM component WHERE process_id = ?;
    """
)

UPSERT_CONNECTOR: str = dedent(
    """\
    INSERT OR REPLACE INTO connector (data, id, process_id) VALUES (?, ?, ?);
    """
)

GET_CONNECTOR: str = dedent(
    """\
    SELECT data FROM connector WHERE id = ?;
    """
)

SET_PROCESS_FOR_CONNECTOR: str = dedent(
    """\
    INSERT INTO process_connector (process_id, connector_id) VALUES (?, ?);
    """
)

GET_PROCESS_FOR_CONNECTOR: str = dedent(
    """\
    SELECT process_id FROM process_connector WHERE connector_id = ?;
    """
)

GET_CONNECTORS_FOR_PROCESS: str = dedent(
    """\
    SELECT id, data FROM connector WHERE process_id = ?;
    """
)

UPDATE_PROCESS_STATUS: str = dedent(
    """\
    UPDATE process SET data = json_set(data, '$.status', ?) WHERE id = ?;
    """
)

GET_PROCESS_STATUS: str = dedent(
    """\
    SELECT json_extract(data, '$.status') AS status FROM process WHERE id = ?;
    """
)

GET_PROCESS_STATUS_FOR_COMPONENT: str = dedent(
    """\
    SELECT json_extract(p.data, '$.status') AS status
    FROM process p
    JOIN process_component pc ON p.id = pc.process_id
    WHERE pc.component_id = ?;
    """
)
