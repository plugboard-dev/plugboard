"""Provides `FileReader` and `FileWriter` components to access files from Plugboard models."""

from collections import deque
from pathlib import Path
import typing as _t

import fsspec
import pandas as pd

from plugboard.exceptions import NoMoreDataException
from .data_reader import DataReader
from .data_writer import DataWriter


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
        """Instantiates the `FileReader`.

        Args:
            name: The name of the `FileReader`.
            path: The path to the file to read.
            field_names: The names of the fields to write to the data source.
            chunk_size: Optional; The size of the data chunks to read from the file.
            storage_options: Optional; Additional options for the fsspec-compatible filesystem.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self._file_path = str(path)
        self._extension = "".join(Path(path).suffixes).lower()
        if self._extension not in {".csv", ".csv.gz", ".parquet"}:
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
                    df_or_reader = pd.read_csv(
                        f,
                        chunksize=self._chunk_size,
                        compression="gzip" if self._extension.endswith("gz") else None,
                    )
                    self._reader = (
                        df_or_reader if self._chunk_size else self._df_chunks(df_or_reader)
                    )
        try:
            return next(self._reader)
        except StopIteration as e:
            raise NoMoreDataException from e

    async def _convert(self, data: pd.DataFrame) -> dict[str, deque]:
        return {field_name: deque(s) for field_name, s in data.items()}


class FileWriter(DataWriter):
    """Writes data to a file.

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
        """Instantiates the `FileWriter`.

        Args:
            name: The name of the `FileWriter`.
            path: The path to the file to read.
            field_names: The names of the fields to write to the data source.
            chunk_size: Optional; The size of the data chunks to read from the file.
            storage_options: Optional; Additional options for the fsspec-compatible filesystem.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self._file_path = str(path)
        self._extension = "".join(Path(path).suffixes).lower()
        if self._extension not in {".csv", ".csv.gz", ".parquet"}:
            raise ValueError(f"Unsupported file format: {self._extension}")
        if self._extension not in {".csv", ".csv.gz"} and self._chunk_size:
            raise ValueError("Only CSV files support chunked writing.")
        self._storage_options = storage_options or {}
        self._header_written = False

    async def _save(self, data: pd.DataFrame) -> None:
        with fsspec.open(self._file_path, **self._storage_options) as f:
            if self._extension == ".parquet":
                data.to_parquet(f, index=False)
            else:
                data.to_csv(
                    f,
                    mode="a",
                    header=not self._header_written,
                    index=False,
                    compression="gzip" if self._extension.endswith("gz") else None,
                )
                self._header_written = True

    async def _convert(self, data: dict[str, deque]) -> pd.DataFrame:
        return pd.DataFrame(data)
