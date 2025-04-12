"""Unit tests for the `SQLReader` and `SQLWriter` components."""

import tempfile
import typing as _t

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from plugboard.connector import AsyncioConnector
from plugboard.exceptions import IOStreamClosedError
from plugboard.library.sql_io import SQLReader, SQLWriter
from plugboard.schemas import ConnectorSpec


class SQLReaderHelper(SQLReader):
    """Helper class to test SQLReader."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.chunk_sizes: list[int] = []

    async def _fetch(self) -> _t.Any:
        result = await super()._fetch()
        self.chunk_sizes.append(len(result))
        return result


@pytest.fixture
def df() -> pd.DataFrame:
    """DataFrame for testing read/write."""
    return pd.DataFrame(
        {"x": [1, 2, 3, 4, 5], "y": [6, 7, 8, 9, 10], "z": ["a", "b", "c", "d", "e"]}
    )


@pytest.fixture
def database_file(df: pd.DataFrame) -> _t.Iterable[str]:
    """Temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db") as file:
        engine = create_engine(f"sqlite:///{file.name}")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE write_test_1 (x INT, y INT, z TEXT)"))
            conn.execute(
                text(
                    "CREATE TABLE write_test_2 (x INT, y INT, z TEXT, alpha INT DEFAULT 0 NOT NULL)"
                )
            )
        df.to_sql("read_test", engine, if_exists="append", index=False)
        yield file.name


@pytest.fixture(params=["sqlite", "sqlite+aiosqlite"])
def connection_string(
    database_file: str, request: pytest.FixtureRequest
) -> _t.Generator[str, None, None]:
    """SQLAlchemy database connection string."""
    yield f"{request.param}:///{database_file}"


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [None, 2, 4, 10])
async def test_sql_reader(
    df: pd.DataFrame, connection_string: str, chunk_size: _t.Optional[int]
) -> None:
    """Test the `FileReader` component."""
    reader = SQLReaderHelper(
        name="sql-reader",
        connection_string=connection_string,
        query="SELECT *, 1 AS something_else FROM read_test",
        field_names=list(df.columns),
        chunk_size=chunk_size,
    )
    await reader.init()

    # Each row of data must be read correctly
    for _, row in df.iterrows():
        await reader.step()
        for field in df.columns:
            assert getattr(reader, field) == row[field]

    # There must be no more data to read
    with pytest.raises(IOStreamClosedError):
        await reader.step()

    # Database driver must return chunks of the correct size
    if chunk_size:
        expected_chunk_sizes = [chunk_size] * (len(df) // chunk_size)
        if len(df) % chunk_size:
            expected_chunk_sizes.append(len(df) % chunk_size)
    else:
        expected_chunk_sizes = [len(df)]
    assert reader.chunk_sizes == expected_chunk_sizes


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [None, 2, 4, 10])
async def test_sql_writer(
    df: pd.DataFrame, connection_string: str, chunk_size: _t.Optional[int], database_file: str
) -> None:
    """Test the `FileWriter` component."""
    writer = SQLWriter(
        name="file-writer",
        connection_string=connection_string,
        table="write_test_1",
        field_names=list(df.columns),
        chunk_size=chunk_size,
    )
    connectors = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"file-writer.{field}"),
        )
        for field in df.columns
    }
    await writer.io.connect(list(connectors.values()))

    await writer.init()

    output_channels = {field: await connectors[field].connect_send() for field in df.columns}
    for _, row in df.iterrows():
        for field in df.columns:
            await output_channels[field].send(row[field])
        await writer.step()

    await writer.io.close()
    await writer.run()

    # Saved data must match the original dataframe
    engine = create_engine(f"sqlite:///{database_file}")
    df_saved = pd.read_sql("SELECT * FROM write_test_1", engine)
    pd.testing.assert_frame_equal(df_saved, df)


@pytest.mark.asyncio
async def test_sql_writer_extra_columns(
    df: pd.DataFrame, connection_string: str, database_file: str
) -> None:
    """Test the `FileWriter` component using a table with extra columns."""
    writer = SQLWriter(
        name="file-writer",
        connection_string=connection_string,
        table="write_test_2",
        field_names=list(df.columns),
    )
    connectors = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"file-writer.{field}"),
        )
        for field in df.columns
    }
    await writer.io.connect(list(connectors.values()))

    await writer.init()

    output_channels = {field: await connectors[field].connect_send() for field in df.columns}
    for _, row in df.iterrows():
        for field in df.columns:
            await output_channels[field].send(row[field])
        await writer.step()

    await writer.io.close()
    await writer.run()

    # Saved data must match the original dataframe
    engine = create_engine(f"sqlite:///{database_file}")
    df_saved = pd.read_sql("SELECT * FROM write_test_2", engine)
    pd.testing.assert_frame_equal(df_saved[df.columns], df)
