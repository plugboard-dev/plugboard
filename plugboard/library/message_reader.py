"""Provides `MessageDataReader` base class for reading data from pub/sub message brokers."""

from __future__ import annotations

from abc import abstractmethod
import asyncio
from collections import deque
import contextlib
import typing as _t

from plugboard.component import IOController
from plugboard.exceptions import IOStreamClosedError, NoMoreDataException
from plugboard.library.data_reader import DataReader
from plugboard.schemas import ComponentArgsDict
from plugboard.utils.retry import RetryPolicy, attempt_reconnect, with_retry


class MessageDataReaderArgsDict(ComponentArgsDict):
    """Specification of the `MessageDataReader` constructor arguments.

    Attributes:
        field_names: The names of the fields to read from messages.
        topic: The topic/queue/subscription to read from.
        chunk_size: Optional; The number of messages to fetch per batch.
        retry_policy: Optional; The backoff policy for retrying failed broker calls.
        idle_poll_delay: Optional; Delay in seconds between polls that return no
            messages.
    """

    field_names: list[str]
    topic: str
    chunk_size: _t.NotRequired[int | None]
    retry_policy: _t.NotRequired[RetryPolicy]
    idle_poll_delay: _t.NotRequired[float]


class MessageDataReader(DataReader):
    """Abstract base class for reading data from a pub/sub message broker.

    Extends [`DataReader`][plugboard.library.DataReader] with the parts a message
    broker needs and a finite source does not: a long-lived connection, reconnection
    with exponential backoff, and acknowledgment of the messages that were consumed.

    Unlike a file or table reader, an empty poll does not mean the stream is over -
    it means the broker had nothing to hand out yet. `step()` therefore waits for the
    next message instead of closing the stream, so a reader started before its
    producer keeps running. A subclass signals a genuinely exhausted source by
    raising [`NoMoreDataException`][plugboard.exceptions.NoMoreDataException] from
    `_receive`, which closes the IO stream like `DataReader` does.

    Subclasses implement the broker-specific methods for connecting, receiving raw
    messages, converting them to field buffers, and acknowledging processed messages.
    """

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        topic: str,
        chunk_size: _t.Optional[int] = None,
        retry_policy: RetryPolicy = RetryPolicy(),
        idle_poll_delay: float = 0.1,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates the `MessageDataReader`.

        Args:
            field_names: The names of the fields to extract from messages.
            topic: The topic/queue/subscription to read from.
            chunk_size: Optional; The number of messages to fetch per batch.
            retry_policy: The backoff policy for retrying failed broker calls.
            idle_poll_delay: Delay in seconds before polling again after a poll that
                returned no messages.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(field_names=field_names, chunk_size=chunk_size, **kwargs)
        self._topic = topic
        self._retry_policy = retry_policy
        self._idle_poll_delay = idle_poll_delay
        self._pending_ack: list[_t.Any] = []
        self._connection_lock = asyncio.Lock()

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

        Should block until at least one message is available or a timeout occurs, and
        return an empty list on timeout. Returning an empty list is *not* how a
        subclass reports an exhausted source - raising `NoMoreDataException` is.

        Returns:
            A list of raw broker-specific message objects.

        Raises:
            NoMoreDataException: If the source is exhausted and no more messages will
                arrive.
            MessageBrokerPermanentError: If the failure cannot be recovered by retrying.
        """
        pass

    @abstractmethod
    async def _ack(self, messages: list[_t.Any]) -> None:
        """Acknowledges successful processing of messages.

        Args:
            messages: The raw messages to acknowledge.
        """
        pass

    @abstractmethod
    async def _convert(self, data: list[_t.Any]) -> dict[str, deque]:
        """Converts raw messages into a `dict[str, deque]` field buffer.

        Args:
            data: Raw broker-specific message objects, as returned by `_receive`.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        pass

    async def _fetch(self) -> list[_t.Any]:
        """Receives a batch of messages, retrying transient failures.

        Returns:
            A list of raw broker-specific message objects, possibly empty.

        Raises:
            NoMoreDataException: If the source is exhausted.
            MessageBrokerConnectionError: If all retries are exhausted.
        """
        return await with_retry(
            self._receive,
            self._reconnect,
            policy=self._retry_policy,
            logger=self._logger,
            description="receiving messages",
        )

    async def _reconnect(self) -> None:
        """Attempts to reconnect to the message broker.

        Held under the connection lock so an in-flight acknowledgment cannot use a
        client that is being replaced.
        """
        async with self._connection_lock:
            await attempt_reconnect(
                self._connect,
                self._disconnect,
                logger=self._logger,
                topic=self._topic,
            )

    async def _fetch_chunk(self) -> None:
        """Fetches a batch of messages and updates the internal buffer.

        An empty batch leaves the buffer untouched, so the caller can poll again: a
        broker with nothing to deliver has not ended the stream. The next batch is
        requested concurrently so that waiting on the broker overlaps with processing.
        """
        if self._task is None:
            self._task = asyncio.create_task(self._fetch())
        task = self._task
        # Clear the reference before awaiting so a failed fetch leaves no dangling task.
        self._task = None
        messages = await task
        if not messages:
            await asyncio.sleep(self._idle_poll_delay)
            return
        new_buffer = await self._convert(messages)
        self._buffer = {field_name: new_buffer[field_name] for field_name in self.io.outputs}
        self._pending_ack = messages
        # Prefetch the next batch while the current one is being consumed.
        self._task = asyncio.create_task(self._fetch())

    @property
    def _records_available(self) -> int:
        """Calculates how many consumed-but-unpublished records the buffer holds."""
        if not self._buffer:
            return 0
        return min(len(values) for values in self._buffer.values())

    async def _ack_pending(self) -> None:
        """Acknowledges the batch whose records have all been consumed.

        Acknowledgment waits for the connection lock, so it never runs against a client
        that a concurrent reconnect is replacing.
        """
        if not self._pending_ack:
            return
        async with self._connection_lock:
            await self._ack(self._pending_ack)
        self._pending_ack = []

    async def init(self) -> None:
        """Initialises the `MessageDataReader`.

        Connects to the message broker and starts pre-fetching the first batch so that
        the first `step()` does not wait on a cold poll.
        """
        await self._connect()
        self._logger.info("Connected to message broker", topic=self._topic)
        self._task = asyncio.create_task(self._fetch())

    async def step(self) -> None:
        """Reads the next message from the broker and updates outputs.

        Waits until a message is available, then consumes one record. Once the batch's
        last record has been consumed the whole batch is acknowledged, so a failure
        before that point leaves the remaining messages for redelivery.

        Raises:
            IOStreamClosedError: If the source is exhausted.
        """
        while not self._records_available:
            try:
                await self._fetch_chunk()
            except NoMoreDataException:
                await self._ack_pending()
                await self.io.close()
                raise IOStreamClosedError("No more messages from broker") from None
        self._consume_record()
        if not self._records_available:
            await self._ack_pending()

    async def destroy(self) -> None:
        """Destroys the `MessageDataReader` and disconnects from the broker.

        Messages that were pre-fetched but never consumed are left unacknowledged so
        the broker redelivers them to whoever reads the queue next.
        """
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        await self._disconnect()
        self._logger.info("Disconnected from message broker", topic=self._topic)
        await super().destroy()
