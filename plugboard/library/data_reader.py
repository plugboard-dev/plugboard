"""Provides components for reading data and feeding into a process model."""

from abc import ABC, abstractmethod
import asyncio
from asyncio.tasks import Task
from collections import deque
import typing as _t

from plugboard.component import Component
from plugboard.component.io_controller import IOController
from plugboard.exceptions import NoMoreDataException


class DataReader(Component, ABC):
    """Abstract base class for reading data."""

    io = IOController()

    def __init__(
        self,
        *args: _t.Any,
        name: str,
        field_names: list[str],
        chunk_size: _t.Optional[int] = None,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates the `DataReader`.

        Args:
            name: The name of the `DataReader`.
            field_names: The names of the fields to read from the data source.
            chunk_size: The size of the data chunk to read from the data source.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(name, *args, **kwargs)
        self._buffer: dict[str, deque] = dict()
        self._chunk_size = chunk_size
        self.io = IOController(inputs=None, outputs=field_names, namespace=name)
        self._task: _t.Optional[Task] = None

    @abstractmethod
    async def _fetch(self) -> _t.Any:
        """Fetches a chunk of data from the underlying source.

        Raises:
            NoMoreDataException: If there is no more data to fetch.
        """
        pass

    @abstractmethod
    async def _convert(self, data: _t.Any) -> dict[str, deque]:
        """Converts the fetched data into a `dict[str, deque]` type used as buffer."""
        pass

    async def _fetch_chunk(self) -> None:
        """Reads data from the buffer."""
        if self._task is None:
            self._task = asyncio.create_task(self._fetch())
        chunk = await self._task
        # Create task to fetch next chunk of data
        self._task = asyncio.create_task(self._fetch())
        new_buffer = await self._convert(chunk)
        self._buffer = {field_name: new_buffer[field_name] for field_name in self.io.outputs}

    async def init(self) -> None:
        """Initialises the `DataReader`."""
        await self._fetch_chunk()

    def _consume_record(self) -> None:
        for field in self.io.outputs:
            setattr(self, field, self._buffer[field].popleft())

    async def step(self) -> None:
        """Reads data from the source and updates outputs."""
        try:
            self._consume_record()
        except IndexError:
            # Buffer is empty, fetch next chunk and try again
            try:
                await self._fetch_chunk()
                self._consume_record()
            except NoMoreDataException:
                await self.io.close()
