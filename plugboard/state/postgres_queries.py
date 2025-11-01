"""PostgreSQL queries for the state module."""

from textwrap import dedent


CREATE_TABLE: str = dedent(
    """\
    CREATE TABLE IF NOT EXISTS job (
        id TEXT PRIMARY KEY,
        data JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ttl INTEGER DEFAULT NULL,
        metadata JSONB GENERATED ALWAYS AS (data->'metadata') STORED,
        status TEXT GENERATED ALWAYS AS (data->>'status') STORED
    );
    CREATE TABLE IF NOT EXISTS process (
        id TEXT PRIMARY KEY,
        data JSONB,
        status TEXT GENERATED ALWAYS AS (data->>'status') STORED,
        job_id TEXT,
        FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS component (
        id TEXT PRIMARY KEY,
        data JSONB,
        status TEXT GENERATED ALWAYS AS (data->>'status') STORED,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS connector (
        id TEXT PRIMARY KEY,
        data JSONB,
        status TEXT GENERATED ALWAYS AS (data->>'status') STORED,
        process_id TEXT,
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_component (
        process_id TEXT NOT NULL,
        component_id TEXT NOT NULL,
        PRIMARY KEY (process_id, component_id),
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE,
        FOREIGN KEY (component_id) REFERENCES component(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS process_connector (
        process_id TEXT NOT NULL,
        connector_id TEXT NOT NULL,
        PRIMARY KEY (process_id, connector_id),
        FOREIGN KEY (process_id) REFERENCES process(id) ON DELETE CASCADE,
        FOREIGN KEY (connector_id) REFERENCES connector(id) ON DELETE CASCADE
    );
    """
)

UPSERT_JOB: str = dedent(
    """\
    INSERT INTO job (id, data) VALUES ($1, $2)
    ON CONFLICT (id) DO UPDATE SET data = $2;
    """
)

GET_JOB: str = dedent(
    """\
    SELECT data FROM job WHERE id = $1;
    """
)

UPSERT_PROCESS: str = dedent(
    """\
    INSERT INTO process (id, data, job_id) VALUES ($1, $2, $3)
    ON CONFLICT (id) DO UPDATE SET data = $2, job_id = $3;
    """
)

GET_PROCESS: str = dedent(
    """\
    SELECT data FROM process WHERE id = $1;
    """
)

UPSERT_COMPONENT: str = dedent(
    """\
    INSERT INTO component (id, data, process_id) VALUES ($1, $2, $3)
    ON CONFLICT (id) DO UPDATE SET data = $2, process_id = $3;
    """
)

GET_COMPONENT: str = dedent(
    """\
    SELECT data FROM component WHERE id = $1;
    """
)

SET_PROCESS_FOR_COMPONENT: str = dedent(
    """\
    INSERT INTO process_component (process_id, component_id) VALUES ($1, $2)
    ON CONFLICT (process_id, component_id) DO NOTHING;
    """
)

GET_PROCESS_FOR_COMPONENT: str = dedent(
    """\
    SELECT process_id FROM process_component WHERE component_id = $1;
    """
)

GET_COMPONENTS_FOR_PROCESS: str = dedent(
    """\
    SELECT id, data FROM component WHERE process_id = $1;
    """
)

UPSERT_CONNECTOR: str = dedent(
    """\
    INSERT INTO connector (id, data, process_id) VALUES ($1, $2, $3)
    ON CONFLICT (id) DO UPDATE SET data = $2, process_id = $3;
    """
)

GET_CONNECTOR: str = dedent(
    """\
    SELECT data FROM connector WHERE id = $1;
    """
)

SET_PROCESS_FOR_CONNECTOR: str = dedent(
    """\
    INSERT INTO process_connector (process_id, connector_id) VALUES ($1, $2)
    ON CONFLICT (process_id, connector_id) DO NOTHING;
    """
)

GET_PROCESS_FOR_CONNECTOR: str = dedent(
    """\
    SELECT process_id FROM process_connector WHERE connector_id = $1;
    """
)

GET_CONNECTORS_FOR_PROCESS: str = dedent(
    """\
    SELECT id, data FROM connector WHERE process_id = $1;
    """
)

UPDATE_PROCESS_STATUS: str = dedent(
    """\
    UPDATE process SET data = jsonb_set(data, '{status}', $1) WHERE id = $2;
    """
)

GET_PROCESS_STATUS: str = dedent(
    """\
    SELECT data->>'status' AS status FROM process WHERE id = $1;
    """
)

GET_PROCESS_STATUS_FOR_COMPONENT: str = dedent(
    """\
    SELECT p.data->>'status' AS status
    FROM process p
    JOIN process_component pc ON p.id = pc.process_id
    WHERE pc.component_id = $1;
    """
)
