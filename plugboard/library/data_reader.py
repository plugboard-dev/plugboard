"""Provides components for reading and writing data to and from a DataFrame."""

from abc import ABC, abstractmethod
import asyncio
from asyncio.tasks import Task
from collections import defaultdict, deque
import typing as _t

from plugboard.component import Component
from plugboard.component.io_controller import IOController
from plugboard.exceptions import IOStreamClosedError, NoMoreDataException


class DataReader(Component, ABC):
    """Reads data from a DataFrame."""

    def __init__(
        self,
        *args: _t.Any,
        name: str,
        field_names: list[str],
        chunk_size: _t.Optional[int],
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates the DataReader."""
        super().__init__(name=name, *args, **kwargs)
        self._buff = defaultdict(deque)
        self._buffer_idx = 0
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
    async def _adapt(self, data: _t.Any) -> dict[str, deque]:
        """Adapts the fetched data into a DataFrame."""
        pass

    async def _fetch_chunk(self) -> None:
        """Reads data from the buffer."""
        if self._task is None:
            self._task = asyncio.create_task(self._fetch())
        chunk = await self._task
        # Create task to fetch next chunk of data
        self._task = asyncio.create_task(self._fetch())
        new_buffer = await self._adapt(chunk)
        self._buffer = {field_name: new_buffer[field_name] for field_name in self.io.outputs}

    async def init(self) -> None:
        """Initialises the `DataReader`."""
        await self._fetch_chunk()

    async def step(self) -> None:
        """Reads data from the DataFrame."""

        def _consume_record() -> None:
            for field in self.io.outputs:
                setattr(self, field, self._buffer[field].popleft())

        try:
            _consume_record()
        except IndexError:
            # Buffer is empty, fetch next chunk and try again
            try:
                await self._fetch_chunk()
                _consume_record()
            except NoMoreDataException as e:
                raise IOStreamClosedError("No more data to read.") from e
