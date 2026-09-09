"""Provides `MessageDataReader` base class for reading data from pub/sub message brokers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from asyncio.tasks import Task
from collections import deque
import typing as _t

from plugboard.component import Component, IOController
from plugboard.exceptions import IOSetupError, IOStreamClosedError, NoMoreDataException
from plugboard.schemas import ComponentArgsDict


class MessageDataReaderArgsDict(ComponentArgsDict):
    """Specification of the `MessageDataReader` constructor arguments.

    Attributes:
        field_names: The names of the fields to read from messages.
        chunk_size: Optional; The number of messages to fetch per batch.
        max_retries: Maximum number of retry attempts for transient failures.
        retry_base_delay: Base delay in seconds for exponential backoff.
        retry_max_delay: Maximum delay in seconds for exponential backoff.
    """

    field_names: list[str]
    topic: _t.NotRequired[str]
    chunk_size: _t.NotRequired[int | None]
    max_retries: _t.NotRequired[int]
    retry_base_delay: _t.NotRequired[float]
    retry_max_delay: _t.NotRequired[float]


class MessageDataReader(Component, ABC):
    """Abstract base class for reading data from a pub/sub message broker.

    Provides connection management, reconnection with exponential backoff,
    retry logic, message acknowledgment, and chunked/buffered reading
    analogous to [`DataReader`][plugboard.library.DataReader].

    Subclasses must implement broker-specific methods for connecting,
    receiving messages, converting messages to field buffers, and
    acknowledging processed messages.
    """

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        topic: str,
        chunk_size: _t.Optional[int] = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates the `MessageDataReader`.

        Args:
            field_names: The names of the fields to extract from messages.
            topic: The topic/queue to read from.
            chunk_size: Optional; The number of messages to fetch per batch.
            max_retries: Maximum number of retry attempts for transient failures.
            retry_base_delay: Base delay in seconds for exponential backoff.
            retry_max_delay: Maximum delay in seconds for exponential backoff.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(**kwargs)
        self._topic = topic
        self._buffer: dict[str, deque] = dict()
        self._chunk_size = chunk_size
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._pending_ack: list[_t.Any] = []
        self._task: _t.Optional[Task] = None
        self.io = IOController(
            inputs=None,
            outputs=field_names,
            input_events=self.__class__.io.input_events,
            output_events=self.__class__.io.output_events,
            namespace=self.name,
            component=self,
        )

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        try:
            return super().__init_subclass__(*args, **kwargs)
        except IOSetupError:
            # Concrete subclasses of the abstract data io classes represent a special case for io
            # setup. They receive io args at run time, not declaration time, so skip error.
            pass

    @abstractmethod
    async def _connect(self) -> None:
        """Establishes connection to the message broker.

        Raises:
            MessageBrokerConnectionError: If connection cannot be established.
        """
        pass

    @abstractmethod
    async def _disconnect(self) -> None:
        """Closes the connection to the message broker."""
        pass

    @abstractmethod
    async def _receive(self) -> list[_t.Any]:
        """Receives a batch of raw messages from the broker.

        Should block until at least one message is available or a timeout occurs.
        Returns an empty list on timeout.

        Returns:
            A list of raw broker-specific message objects.

        Raises:
            NoMoreDataException: If the subscription/source is exhausted and no
                more messages will arrive.
        """
        pass

    @abstractmethod
    async def _convert(self, messages: list[_t.Any]) -> dict[str, deque]:
        """Converts raw messages into a `dict[str, deque]` field buffer.

        Args:
            messages: Raw broker-specific message objects.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        pass

    @abstractmethod
    async def _ack(self, messages: list[_t.Any]) -> None:
        """Acknowledges successful processing of messages.

        Args:
            messages: The raw messages to acknowledge.
        """
        pass

    async def _receive_with_retry(self) -> list[_t.Any]:
        """Receives messages with exponential backoff retry and reconnection.

        Returns:
            A list of raw broker-specific message objects.

        Raises:
            NoMoreDataException: If the source is exhausted.
            MessageBrokerConnectionError: If all retries are exhausted.
        """
        last_exception: Exception = RuntimeError("All retries exhausted")
        for attempt in range(self._max_retries + 1):
            try:
                return await self._receive()
            except NoMoreDataException:
                raise
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries:
                    delay = min(
                        self._retry_base_delay * (2**attempt),
                        self._retry_max_delay,
                    )
                    self._logger.warning(
                        "Transient error receiving messages, retrying",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                    await self._reconnect()
        raise last_exception

    async def _reconnect(self) -> None:
        """Attempts to reconnect to the message broker."""
        self._logger.info("Attempting reconnection to message broker", topic=self._topic)
        try:
            await self._disconnect()
        except Exception:  # noqa: S110
            self._logger.warning("Error during disconnect in reconnection", exc_info=True)
        await self._connect()
        self._logger.info("Reconnected to message broker", topic=self._topic)

    async def _fetch_batch(self) -> None:
        """Fetches a batch of messages and updates the internal buffer."""
        if self._task is None:
            self._task = asyncio.create_task(self._receive_with_retry())
        messages = await self._task
        # Start fetching next batch concurrently
        self._task = asyncio.create_task(self._receive_with_retry())
        if len(messages) == 0:
            raise NoMoreDataException
        new_buffer = await self._convert(messages)
        self._buffer = {field_name: new_buffer[field_name] for field_name in self.io.outputs}
        self._pending_ack = messages

    def _consume_record(self) -> None:
        """Consumes one record from the buffer and sets field attributes."""
        for field in self.io.outputs:
            setattr(self, field, self._buffer[field].popleft())

    async def _ack_pending(self) -> None:
        """Acknowledges all pending messages."""
        if self._pending_ack:
            await self._ack(self._pending_ack)
            self._pending_ack = []

    async def init(self) -> None:
        """Initialises the `MessageDataReader`.

        Connects to the message broker and pre-fetches the first batch of messages.
        If no messages are available, the reader will raise `IOStreamClosedError`
        on the first `step()` call.
        """
        await self._connect()
        self._logger.info("Connected to message broker", topic=self._topic)
        try:
            await self._fetch_batch()
        except NoMoreDataException:
            # No messages available at init time; step() will raise IOStreamClosedError
            pass

    async def step(self) -> None:
        """Reads data from the message broker and updates outputs.

        Consumes one record from the buffer. If the buffer is empty,
        fetches the next batch. Acknowledges processed messages.

        Raises:
            IOStreamClosedError: If there is no more data to read.
        """
        if not self._buffer:
            # Buffer was never populated (e.g. empty source at init)
            await self.io.close()
            raise IOStreamClosedError("No more messages from broker")
        try:
            self._consume_record()
            await self._ack_pending()
        except IndexError:
            try:
                await self._fetch_batch()
                self._consume_record()
                await self._ack_pending()
            except NoMoreDataException:
                await self.io.close()
                raise IOStreamClosedError("No more messages from broker")

    async def destroy(self) -> None:
        """Destroys the `MessageDataReader` and disconnects from the broker."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: S110
                pass
            self._task = None
        await self._disconnect()
        self._logger.info("Disconnected from message broker", topic=self._topic)
        await super().destroy()
