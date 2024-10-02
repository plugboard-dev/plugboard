"""Provides `FileReader` class to load data from files."""

from collections import deque
from pathlib import Path
import typing as _t

import fsspec
import pandas as pd

from plugboard.exceptions import NoMoreDataException
from .data_reader import DataReader


class FileReader(DataReader):
    """Reads data from a file.

    Support formats: CSV, GZIP-compressed CSV, Parquet.
    The file can be stored locally or on an fsspec-compatible cloud storage service.
    """

    def __init__(
        self,
        *args: _t.Any,
        path: str | Path,
        storage_options: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._file_path = Path(path)
        self._extension = "".join(self._file_path.suffixes).lower()
        if self._extension not in [".csv", ".csv.gz", ".parquet"]:
            raise ValueError(f"Unsupported file format: {self._extension}")
        self._storage_options = storage_options or {}
        self._reader: _t.Optional[pd.io.parsers.TextFileReader | _t.Iterator[pd.DataFrame]] = None

    @classmethod
    def _df_chunks(
        cls, df: pd.DataFrame, chunk_size: _t.Optional[int] = None
    ) -> _t.Iterator[pd.DataFrame]:
        chunk_size = chunk_size or len(df)
        for i in range(0, len(df), chunk_size):
            yield df.iloc[i : i + chunk_size]

    async def _fetch(self) -> pd.DataFrame:
        if self._reader is None:
            with fsspec.open(self._file_path, **self._storage_options) as f:
                if self._extension == ".parquet":
                    self._reader = self._df_chunks(pd.read_parquet(f), chunk_size=self._chunk_size)
                else:
                    self._reader = pd.read_csv(f, chunksize=self._chunk_size)
        try:
            return next(self._reader)
        except StopIteration as e:
            raise NoMoreDataException from e

    async def _convert(self, data: pd.DataFrame) -> dict[str, deque]:
        return {field_name: deque(s) for field_name, s in data.items()}
