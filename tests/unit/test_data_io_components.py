"""Unit tests for the DataReader class."""

from collections import deque
import typing as _t

import pandas as pd
import pytest

from plugboard.component.io_controller import IOController
from plugboard.connector import AsyncioChannel, Connector
from plugboard.exceptions import IOStreamClosedError, NoMoreDataException
from plugboard.library import DataReader, DataWriter
from plugboard.schemas import ConnectorSpec


@pytest.fixture
def df() -> pd.DataFrame:
    """Dataframe for testing."""
    return pd.DataFrame(
        {"x": [1, 2, 3, 4, 5], "y": [6, 7, 8, 9, 10], "z": ["a", "b", "c", "d", "e"]}
    )


class MockDataReader(DataReader):
    """Mock DataReader class for testing purposes."""

    io: IOController = IOController(inputs=None, outputs=["x", "z"])

    def __init__(self, *args: _t.Any, df: pd.DataFrame, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._df = df
        self._idx = 0
        self.total_fetches = 0

    async def _fetch(self) -> pd.DataFrame:
        if self._chunk_size:
            df_chunk = self._df.iloc[self._idx : self._idx + self._chunk_size]
        else:
            df_chunk = self._df[self._idx :]
        self._idx += len(df_chunk)
        self.total_fetches += 1
        if df_chunk.empty:
            raise NoMoreDataException
        return df_chunk

    async def _adapt(self, data: pd.DataFrame) -> dict[str, deque]:
        return {field_name: deque(s) for field_name, s in data.items()}


class MockDataWriter(DataWriter):
    """Mock DataWriter class for testing purposes."""

    io: IOController = IOController(inputs=["x", "y", "z"], outputs=None)

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.df = pd.DataFrame()
        self.total_saves = 0

    async def _save(self, data: pd.DataFrame) -> None:
        self.df = pd.concat([self.df, data])
        self.total_saves += 1

    async def _adapt(self, data: dict[str, deque]) -> pd.DataFrame:
        return pd.DataFrame(data)


@pytest.mark.anyio
@pytest.mark.parametrize("chunk_size", [None, 2, 10])
@pytest.mark.parametrize("field_names", [["x", "z"], ["x", "y", "z"]])
async def test_data_reader(
    df: pd.DataFrame, chunk_size: _t.Optional[int], field_names: list[str]
) -> None:
    """Test the DataReader class."""
    reader = MockDataReader(
        name="data_reader", field_names=field_names, chunk_size=chunk_size, df=df
    )
    await reader.init()
    # Init must trigger first data fetch
    assert reader.total_fetches == 1
    results = []
    while True:
        try:
            await reader.step()
            results.append(reader.dict()["output"].copy())
        except IOStreamClosedError:
            break
    df_results = pd.DataFrame(results)
    # Returned data must be correct
    pd.testing.assert_frame_equal(df_results, df[field_names])
    # Total fetches must match number of chunks + 1 for the final empty chunk
    assert reader.total_fetches == -(len(df) // -(chunk_size or len(df))) + 1


@pytest.mark.anyio
@pytest.mark.parametrize("chunk_size", [None, 2, 10])
async def test_data_writer(
    df: pd.DataFrame,
    chunk_size: _t.Optional[int],
) -> None:
    """Test the DataWriter class."""
    writer = MockDataWriter(name="data_writer", chunk_size=chunk_size)
    connectors = {
        field: Connector(
            spec=ConnectorSpec(source="none.none", target=f"data_writer.{field}"),
            channel=AsyncioChannel(),
        )
        for field in df.columns
    }
    writer.io.connect(connectors.values())

    await writer.init()

    for _, row in df.iterrows():
        for field in df.columns:
            await connectors[field].channel.send(row[field])
        await writer.step()

    await writer.io.close()
    await writer.run()
