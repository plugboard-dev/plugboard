"""Unit tests for the DataReader class."""

from collections import deque
import typing as _t

import pandas as pd
import pytest

from plugboard.component.io_controller import IOController
from plugboard.exceptions import IOStreamClosedError, NoMoreDataException
from plugboard.library import DataReader


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


@pytest.mark.anyio
@pytest.mark.parametrize("chunk_size", [None, 2, 10])
@pytest.mark.parametrize("field_names", [["x", "z"], ["x", "y", "z"]])
async def test_data_reader(chunk_size: _t.Optional[int], field_names: list[str]) -> None:
    """Test the DataReader class."""
    df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [6, 7, 8, 9, 10], "z": ["a", "b", "c", "d", "e"]})
    reader = MockDataReader(
        name="data-reader", field_names=field_names, chunk_size=chunk_size, df=df
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
