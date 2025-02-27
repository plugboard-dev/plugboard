"""Provides `SQLReader` and `SQLWriter` components to access SQL databases from Plugboard models."""

from collections import defaultdict, deque
import typing as _t

from sqlalchemy import MetaData, Table, insert, text
from sqlalchemy.engine import Engine, Row, create_engine
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from plugboard.exceptions import NoMoreDataException
from .data_reader import DataReader, DataReaderArgsSpec
from .data_writer import DataWriter, DataWriterArgsSpec


class SQLReader(DataReader):
    """Reads data from an SQL database using a supplied query and optional parameters.

    The underlying database connection is managed by SQLAlchemy: both synchronous and asynchronous
    drivers are supported.
    """

    def __init__(
        self,
        connection_string: str,
        query: str,
        params: _t.Optional[dict[str, _t.Any]] = None,
        connect_args: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Unpack[DataReaderArgsSpec],
    ) -> None:
        """Instantiates the `SQLReader`.

        Args:
            connection_string: The connection string for the database.
            query: The SQL query to run on the database.
            params: Optional; Parameters to pass to the query.
            connect_args: Optional; Additional options for the database connection.
            **kwargs: Additional keyword arguments for [`DataReader`][plugboard.library.DataReader].
        """
        super().__init__(**kwargs)
        self._connection_string = connection_string
        self._query = query
        self._params = params or {}
        self._reader: _t.Optional[_t.AsyncIterator | _t.Iterator] = None
        self._connect_args = connect_args or {}

    async def _run_query_async(self) -> _t.AsyncIterator[_t.Sequence[Row]]:
        engine = create_async_engine(self._connection_string, **self._connect_args)
        async with engine.connect() as conn:
            if self._chunk_size:
                # Use server-side cursor for large datasets
                streamer = await conn.execution_options(
                    stream_results=True, max_row_buffer=self._chunk_size
                )
                result_stream = await streamer.stream(text(self._query).params(self._params))
                async for batch in result_stream.partitions(self._chunk_size):
                    yield batch
            else:
                # Driver will fetch all results at once
                result = await conn.execute(text(self._query).params(self._params))
                yield list(result)
            raise NoMoreDataException

    def _run_query_sync(self) -> _t.Iterator[_t.Sequence[Row]]:
        engine = create_engine(self._connection_string, **self._connect_args)
        with engine.connect() as conn:
            if self._chunk_size:
                # Use server-side cursor for large datasets
                streamer = conn.execution_options(
                    stream_results=True, max_row_buffer=self._chunk_size
                )
                result_stream = streamer.execute(text(self._query).params(self._params))
                for batch in result_stream.partitions(self._chunk_size):
                    yield batch
            else:
                result = conn.execute(text(self._query).params(self._params))
                yield list(result)
            raise NoMoreDataException

    async def _fetch(self) -> _t.Sequence[Row]:
        if self._reader is None:
            try:
                self._reader = self._run_query_async()
                return await self._reader.__anext__()
            except InvalidRequestError:
                # Fall back on synchronous connection
                self._reader = self._run_query_sync()
                return next(self._reader)

        if isinstance(self._reader, _t.AsyncIterator):
            return await self._reader.__anext__()
        return next(self._reader)

    async def _convert(self, data: _t.Sequence[Row]) -> dict[str, deque]:
        converted_data: dict[str, deque] = defaultdict(deque)
        for row in data:
            for field_name in self.io.outputs:
                converted_data[field_name].append(getattr(row, field_name))
        return converted_data


class SQLWriter(DataWriter):
    """Writes data to an SQL database. The specified table must already exist.

    The underlying database connection is managed by SQLAlchemy: both synchronous and asynchronous
    drivers are supported.
    """

    def __init__(
        self,
        connection_string: str,
        table: str,
        connect_args: _t.Optional[dict[str, _t.Any]] = None,
        **kwargs: _t.Unpack[DataWriterArgsSpec],
    ) -> None:
        """Instantiates the `SQLWriter`.

        Args:
            connection_string: The connection string for the database.
            table: The name of the table to write to, which must already exist.
            connect_args: Optional; Additional options for the database connection.
            **kwargs: Additional keyword arguments for [`DataWriter`][plugboard.library.DataWriter].
        """
        super().__init__(**kwargs)
        self._connection_string = connection_string
        self._table_name = table
        self._connect_args = {
            "isolation_level": "AUTOCOMMIT",
            "pool_pre_ping": True,
            **(connect_args or {}),
        }
        self._metadata = MetaData()
        self._table: _t.Optional[Table] = None
        self._engine: _t.Optional[AsyncEngine | Engine] = None

    async def _save_rows_async(self, data: list[dict[str, _t.Any]]) -> None:
        if not isinstance(self._engine, AsyncEngine):
            raise RuntimeError("No async database connection available")
        async with self._engine.connect() as conn:
            if self._table is None:
                await conn.run_sync(
                    self._metadata.reflect,
                    only=[self._table_name],
                )
                self._table = Table(self._table_name, self._metadata, autoload_with=self._engine)  # type: ignore[arg-type]
            await conn.execute(insert(self._table).values(data))

    def _save_rows_sync(self, data: list[dict[str, _t.Any]]) -> None:
        if not isinstance(self._engine, Engine):
            raise RuntimeError("No sync database connection available")
        with self._engine.connect() as conn:
            if self._table is None:
                self._metadata.reflect(only=[self._table_name], bind=self._engine)
                self._table = Table(self._table_name, self._metadata, autoload_with=self._engine)
            conn.execute(insert(self._table), data)

    async def _save(self, data: list[dict[str, _t.Any]]) -> None:
        if not self._engine:
            try:
                self._engine = create_async_engine(self._connection_string, **self._connect_args)
            except InvalidRequestError:
                # Fall back on synchronous connection
                self._engine = create_engine(self._connection_string, **self._connect_args)
        if isinstance(self._engine, AsyncEngine):
            await self._save_rows_async(data)
        else:
            self._save_rows_sync(data)

    async def _convert(self, data: dict[str, deque]) -> list[dict[str, _t.Any]]:
        return [dict(zip(data, t)) for t in zip(*data.values())]
