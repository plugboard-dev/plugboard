"""Provides components for reading data and feeding into a process model."""

from abc import ABC, abstractmethod
import asyncio
from asyncio.tasks import Task
from collections import deque
import typing as _t

from plugboard.component import Component
from plugboard.component.io_controller import IOController
from plugboard.exceptions import IOSetupError, NoMoreDataException
from plugboard.schemas import ComponentArgsDict


class DataReaderArgsSpec(ComponentArgsDict):
    """Specification of the `DataReader` constructor arguments.

    Attributes:
        field_names: The names of the fields to read from the data source.
        chunk_size: Optional; The size of the data chunk to read from the data source.
    """

    field_names: list[str]
    chunk_size: _t.NotRequired[int | None]


class DataReader(Component, ABC):
    """Abstract base class for reading data."""

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        chunk_size: _t.Optional[int] = None,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates the `DataReader`.

        Args:
            field_names: The names of the fields to read from the data source.
            chunk_size: The size of the data chunk to read from the data source.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(**kwargs)
        self._buffer: dict[str, deque] = dict()
        self._chunk_size = chunk_size
        self.io = IOController(
            inputs=None,
            outputs=field_names,
            input_events=self.__class__.io.input_events,
            output_events=self.__class__.io.output_events,
            namespace=self.name,
            component=self,
        )
        self._task: _t.Optional[Task] = None

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        try:
            return super().__init_subclass__(*args, **kwargs)
        except IOSetupError:
            # Concrete subclasses of the abstract data io classes represent a special case for io
            # setup. They receive io args at run time, not declaration time, so skip error.
            pass

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
