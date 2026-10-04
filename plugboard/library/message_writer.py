"""Provides `MessageDataWriter` base class for writing data to pub/sub message brokers."""

from __future__ import annotations

from abc import abstractmethod
import asyncio
from collections import deque
import json
import typing as _t

from plugboard.component import IOController
from plugboard.library.data_writer import DataWriter
from plugboard.schemas import ComponentArgsDict
from plugboard.utils.retry import RetryPolicy, attempt_reconnect, with_retry


class MessageDataWriterArgsDict(ComponentArgsDict):
    """Specification of the `MessageDataWriter` constructor arguments.

    Attributes:
        field_names: The names of the fields to include in messages.
        topic: The topic/queue to write to.
        chunk_size: Optional; The number of records to batch into each send.
        retry_policy: Optional; The backoff policy for retrying failed broker calls.
    """

    field_names: list[str]
    topic: str
    chunk_size: _t.NotRequired[int | None]
    retry_policy: _t.NotRequired[RetryPolicy]


def iter_records(data: dict[str, deque]) -> _t.Iterator[dict[str, _t.Any]]:
    """Iterates over the complete records held in a field buffer.

    Zipping the deques walks each field once, which keeps record building linear in
    the number of buffered values - indexing the deques per row would be quadratic,
    and with the default `chunk_size` the buffer holds the whole run.

    Args:
        data: A dictionary mapping field names to deques of field values.

    Yields:
        One dictionary per complete record, keyed by field name.
    """
    fields = tuple(data)
    if not fields:
        return
    for row in zip(*data.values()):
        yield dict(zip(fields, row))


def _raw_value(record: dict[str, _t.Any]) -> str:
    """Returns the first field of a record as text, for non-JSON payloads."""
    value = next(iter(record.values()))
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _raw_bytes(record: dict[str, _t.Any]) -> bytes:
    """Returns the first field of a record as bytes, for non-JSON payloads.

    Byte values are passed through unchanged so binary payloads are not corrupted by
    a text round trip.
    """
    value = next(iter(record.values()))
    return bytes(value) if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")


def encode_records(data: dict[str, deque], parse_json: bool) -> list[str]:
    """Encodes a field buffer as one text message per record.

    Args:
        data: A dictionary mapping field names to deques of field values.
        parse_json: Whether to encode each record as a JSON object. When false, the
            first field's value is used as the message body.

    Returns:
        A list of message strings ready to send.
    """
    return [
        json.dumps(record) if parse_json else _raw_value(record) for record in iter_records(data)
    ]


def encode_records_bytes(data: dict[str, deque], parse_json: bool) -> list[bytes]:
    """Encodes a field buffer as one binary message per record.

    Args:
        data: A dictionary mapping field names to deques of field values.
        parse_json: Whether to encode each record as a JSON object. When false, the
            first field's value is used as the message body.

    Returns:
        A list of bytes objects ready to send.
    """
    return [
        json.dumps(record).encode("utf-8") if parse_json else _raw_bytes(record)
        for record in iter_records(data)
    ]


class MessageDataWriter(DataWriter):
    """Abstract base class for writing data to a pub/sub message broker.

    Extends [`DataWriter`][plugboard.library.DataWriter] with the parts a message
    broker needs and a file or table does not: a long-lived connection, and
    reconnection with exponential backoff around each send. Buffered records are
    batched into messages by the broker-specific `_convert`.

    Subclasses implement the broker-specific methods for connecting, sending encoded
    messages, and converting field data to the broker's message format.
    """

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        topic: str,
        chunk_size: _t.Optional[int] = None,
        retry_policy: RetryPolicy = RetryPolicy(),
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates the `MessageDataWriter`.

        Args:
            field_names: The names of the fields to include in messages.
            topic: The topic/queue to write to.
            chunk_size: Optional; The number of records to batch into a single send.
            retry_policy: The backoff policy for retrying failed broker calls.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(field_names=field_names, chunk_size=chunk_size, **kwargs)
        self._topic = topic
        self._retry_policy = retry_policy

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
            MessageBrokerConnectionError: If the connection to the broker fails.
            MessageBrokerPermanentError: If the messages cannot be delivered and
                retrying cannot help.
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

    async def _save(self, data: list[_t.Any]) -> None:
        """Sends encoded messages to the broker, retrying transient failures.

        Args:
            data: The converted messages to send, as produced by `_convert`.

        Raises:
            MessageBrokerConnectionError: If all retries are exhausted.
        """
        await with_retry(
            lambda: self._send(data),
            self._reconnect,
            policy=self._retry_policy,
            logger=self._logger,
            description="sending messages",
        )

    async def _reconnect(self) -> None:
        """Attempts to reconnect to the message broker.

        No lock is needed here: unlike a reader, a writer never acknowledges
        concurrently, and sends are serialised through `self._task`.
        """
        await attempt_reconnect(
            self._connect,
            self._disconnect,
            logger=self._logger,
            topic=self._topic,
        )

    async def init(self) -> None:
        """Initialises the `MessageDataWriter` by connecting to the message broker."""
        await self._connect()
        self._logger.info("Connected to message broker", topic=self._topic)

    async def destroy(self) -> None:
        """Destroys the `MessageDataWriter` and disconnects from the broker.

        Any send still in flight is awaited rather than cancelled, so buffered data is
        not lost on teardown.
        """
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except Exception as error:  # noqa: BLE001
                self._logger.warning("Pending send failed during destroy", error=str(error))
            self._task = None
        await self._disconnect()
        self._logger.info("Disconnected from message broker", topic=self._topic)
        await super().destroy()
