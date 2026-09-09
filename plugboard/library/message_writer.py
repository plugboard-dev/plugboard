"""Provides `MessageDataWriter` base class for writing data to pub/sub message brokers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from asyncio.tasks import Task
from collections import defaultdict, deque
import typing as _t

from plugboard.component import Component, IOController
from plugboard.exceptions import IOSetupError
from plugboard.schemas import ComponentArgsDict


class MessageDataWriterArgsDict(ComponentArgsDict):
    """Specification of the `MessageDataWriter` constructor arguments.

    Attributes:
        field_names: The names of the fields to include in messages.
        chunk_size: Optional; The number of records to batch into messages.
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


class MessageDataWriter(Component, ABC):
    """Abstract base class for writing data to a pub/sub message broker.

    Provides connection management, reconnection with exponential backoff,
    retry logic, and chunked/buffered writing analogous to
    [`DataWriter`][plugboard.library.DataWriter].

    Subclasses must implement broker-specific methods for connecting,
    sending messages, and converting field data to broker-specific
    message format.
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
        """Instantiates the `MessageDataWriter`.

        Args:
            field_names: The names of the fields to include in messages.
            topic: The topic/queue to write to.
            chunk_size: Optional; The number of records to batch into a single send operation.
            max_retries: Maximum number of retry attempts for transient failures.
            retry_base_delay: Base delay in seconds for exponential backoff.
            retry_max_delay: Maximum delay in seconds for exponential backoff.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(**kwargs)
        self._topic = topic
        self._buffer: dict[str, deque] = defaultdict(deque)
        self._chunk_size = chunk_size
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._task: _t.Optional[Task] = None
        self.io = IOController(
            inputs=field_names,
            outputs=None,
            input_events=self.__class__.io.input_events,
            output_events=self.__class__.io.output_events,
            event_field_coverage=self.__class__.io.event_field_coverage,
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
    async def _send(self, messages: list[_t.Any]) -> None:
        """Sends a batch of messages to the broker.

        Args:
            messages: A list of broker-specific message objects to send.

        Raises:
            MessageBrokerConnectionError: If messages cannot be sent.
        """
        pass

    @abstractmethod
    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data into broker-specific message format.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of broker-specific message objects ready to send.
        """
        pass

    async def _send_with_retry(self, messages: list[_t.Any]) -> None:
        """Sends messages with exponential backoff retry and reconnection.

        Args:
            messages: The messages to send.

        Raises:
            Exception: If all retries are exhausted.
        """
        last_exception: Exception = RuntimeError("All retries exhausted")
        for attempt in range(self._max_retries + 1):
            try:
                await self._send(messages)
                return
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries:
                    delay = min(
                        self._retry_base_delay * (2**attempt),
                        self._retry_max_delay,
                    )
                    self._logger.warning(
                        "Transient error sending messages, retrying",
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
        except Exception:  # noqa: S102
            self._logger.warning("Error during disconnect in reconnection", exc_info=True)
        await self._connect()
        self._logger.info("Reconnected to message broker", topic=self._topic)

    def _bind_inputs(self) -> None:
        """Binds input fields to component fields and appends to internal buffer."""
        super()._bind_inputs()
        for field in self._field_inputs:
            value = getattr(self, field, None)
            self._buffer[field].append(value)

    @property
    def _completed_rows(self) -> int:
        """Calculates how many fully formed rows exist in the buffer."""
        if not self.io.inputs:
            return 0
        return min((len(self._buffer[f]) for f in self.io.inputs), default=0)

    @property
    def _can_step(self) -> bool:
        """We can step if we have at least one fully formed row."""
        return self._completed_rows > 0

    async def _send_batch(self) -> None:
        """Sends completed data rows from the buffer."""
        completed_rows = self._completed_rows
        if completed_rows == 0:
            return

        if self._task is not None:
            await self._task

        # Extract only the completed rows into a new chunk
        chunk_data: dict[str, deque] = {
            field: deque([self._buffer[field].popleft() for _ in range(completed_rows)])
            for field in self.io.inputs
        }

        messages = await self._convert(chunk_data)
        self._task = asyncio.create_task(self._send_with_retry(messages))

    async def init(self) -> None:
        """Initialises the `MessageDataWriter`.

        Connects to the message broker.
        """
        await self._connect()
        self._logger.info("Connected to message broker", topic=self._topic)

    async def step(self) -> None:
        """Triggers send when buffer is at target size.

        If `chunk_size` is set and the buffer has reached that size,
        sends the buffered data as messages.
        """
        if self._chunk_size and self._completed_rows >= self._chunk_size:
            await self._send_batch()

    async def run(self) -> None:
        """Runs the `MessageDataWriter`.

        Steps until all input is consumed, then flushes any remaining
        buffered data.
        """
        await super().run()
        # Flush any remaining data in the buffer after completion
        await self._send_batch()
        if self._task is not None:
            await self._task

    async def destroy(self) -> None:
        """Destroys the `MessageDataWriter` and disconnects from the broker."""
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
