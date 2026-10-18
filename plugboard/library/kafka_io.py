"""Provides `KafkaDataReader` and `KafkaDataWriter` for Apache Kafka messaging."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import typing as _t

from plugboard.exceptions import (
    MessageBrokerConnectionError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
)
from plugboard.library.message_reader import MessageDataReader, MessageDataReaderArgsDict
from plugboard.library.message_writer import (
    MessageDataWriter,
    MessageDataWriterArgsDict,
    encode_records_bytes,
)
from plugboard.utils import DI, depends_on_optional
from plugboard.utils.settings import resolve_argument


try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.errors import (
        CoordinatorNotAvailableError,
        KafkaConnectionError,
        NodeNotReadyError,
        NotLeaderForPartitionError,
        RecordTooLargeError,
        RequestTimedOutError,
        TopicAuthorizationFailedError,
        UnknownTopicOrPartitionError,
    )
    from aiokafka.structs import OffsetAndMetadata, TopicPartition

    # Kafka failures that retrying cannot resolve, such as missing authorization or a
    # record the broker will always reject.
    _PERMANENT_ERRORS: tuple[type[Exception], ...] = (
        TopicAuthorizationFailedError,
        RecordTooLargeError,
    )

    # Kafka failures raised while the cluster is rebalancing or a broker is unreachable,
    # which are expected to clear.
    _TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
        KafkaConnectionError,
        NodeNotReadyError,
        CoordinatorNotAvailableError,
        NotLeaderForPartitionError,
        RequestTimedOutError,
        UnknownTopicOrPartitionError,
    )
except ImportError:  # pragma: no cover
    # With the extra not installed, `depends_on_optional` blocks construction and
    # classification is moot: `isinstance(error, ())` never matches.
    _PERMANENT_ERRORS = ()
    _TRANSIENT_ERRORS = ()


def _wrap_error(error: Exception) -> Exception:
    """Maps an aiokafka error onto the Plugboard message broker exception hierarchy.

    Args:
        error: The error raised by the Kafka client.

    Returns:
        A `MessageBrokerPermanentError` for a rejection that will not change on retry,
        a `MessageBrokerTransientError` for a failure worth retrying, otherwise the
        original error.
    """
    if isinstance(error, _PERMANENT_ERRORS):
        return MessageBrokerPermanentError(str(error))
    if isinstance(error, _TRANSIENT_ERRORS):
        return MessageBrokerTransientError(str(error))
    return error


class KafkaDataReader(MessageDataReader):
    """Reads data from an Apache Kafka topic.

    Messages are consumed from the topic using a consumer group. Acknowledging a batch
    commits the offsets following the records that were consumed, so a failure before
    that point leaves the remaining records for redelivery.
    """

    @depends_on_optional("aiokafka", extra="kafka")
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: _t.Optional[str | list[str]] = None,
        parse_json: bool = True,
        poll_timeout_ms: int = 30_000,
        **kwargs: _t.Unpack[MessageDataReaderArgsDict],
    ) -> None:
        """Instantiates the `KafkaDataReader`.

        Args:
            group_id: Consumer group ID.
            bootstrap_servers: Optional; Kafka broker address(es), for example
                `"localhost:9092"`. Falls back to `KAFKA_BOOTSTRAP_SERVERS`.
            parse_json: Whether to parse message values as JSON.
            poll_timeout_ms: Milliseconds to wait for a batch of records.
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        bootstrap_servers = resolve_argument(
            bootstrap_servers,
            DI.settings.resolve_sync().kafka.bootstrap_servers,
            "bootstrap_servers",
            "KAFKA_BOOTSTRAP_SERVERS",
        )
        super().__init__(**kwargs)
        self._bootstrap_servers = (
            [bootstrap_servers] if isinstance(bootstrap_servers, str) else bootstrap_servers
        )
        self._group_id = group_id
        self._parse_json = parse_json
        self._poll_timeout_ms = poll_timeout_ms
        self._consumer: _t.Optional[AIOKafkaConsumer] = None

    async def _connect(self) -> None:
        """Creates and starts a Kafka consumer."""
        consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_records=self._chunk_size or 10,
        )
        await consumer.start()
        self._consumer = consumer

    async def _disconnect(self) -> None:
        """Stops and closes the Kafka consumer."""
        if self._consumer is not None:
            consumer = self._consumer
            self._consumer = None
            await consumer.stop()

    async def _receive(self) -> list[_t.Any]:
        """Receives a batch of messages from the Kafka topic.

        Returns:
            A list of Kafka `ConsumerRecord` objects, empty if the poll timed out.

        Raises:
            MessageBrokerError: If the poll failed for a retryable or permanent reason.
        """
        if self._consumer is None:
            raise MessageBrokerConnectionError("Kafka consumer is not connected")
        max_messages = self._chunk_size or 10
        try:
            data = await self._consumer.getmany(
                timeout_ms=self._poll_timeout_ms, max_records=max_messages
            )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error
        return [record for records in data.values() for record in records]

    async def _convert(self, data: list[_t.Any]) -> dict[str, deque]:
        """Converts Kafka messages to a field buffer.

        Args:
            data: A list of `ConsumerRecord` objects.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for record in data:
            value = record.value
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            if self._parse_json:
                record_data = json.loads(value)
            else:
                record_data = {"data": value}
            for field in self.io.outputs:
                converted[field].append(record_data.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        """Commits the offsets that follow the processed Kafka messages.

        Only the offsets of the records that were actually consumed are committed, so
        records still waiting in the buffer stay eligible for redelivery.

        Args:
            messages: The `ConsumerRecord` objects that have been processed.

        Raises:
            MessageBrokerConnectionError: If the consumer is not connected.
            MessageBrokerError: If the commit failed.
        """
        if self._consumer is None:
            raise MessageBrokerConnectionError("Kafka consumer is not connected")
        offsets: dict[TopicPartition, OffsetAndMetadata] = {}
        for record in messages:
            partition = TopicPartition(record.topic, record.partition)
            next_offset = OffsetAndMetadata(record.offset + 1, "")
            current = offsets.get(partition)
            if current is None or current.offset < next_offset.offset:
                offsets[partition] = next_offset
        if not offsets:
            return
        try:
            await self._consumer.commit(offsets=offsets)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error


class KafkaDataWriter(MessageDataWriter):
    """Writes data to an Apache Kafka topic.

    Field data is converted to JSON-encoded messages and produced to the specified
    topic. Records are submitted together and flushed once, so the producer's internal
    batching is used instead of one round trip per record.
    """

    @depends_on_optional("aiokafka", extra="kafka")
    def __init__(
        self,
        bootstrap_servers: _t.Optional[str | list[str]] = None,
        parse_json: bool = True,
        **kwargs: _t.Unpack[MessageDataWriterArgsDict],
    ) -> None:
        """Instantiates the `KafkaDataWriter`.

        Args:
            bootstrap_servers: Optional; Kafka broker address(es), for example
                `"localhost:9092"`. Falls back to `KAFKA_BOOTSTRAP_SERVERS`.
            parse_json: Whether to encode message values as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        bootstrap_servers = resolve_argument(
            bootstrap_servers,
            DI.settings.resolve_sync().kafka.bootstrap_servers,
            "bootstrap_servers",
            "KAFKA_BOOTSTRAP_SERVERS",
        )
        super().__init__(**kwargs)
        self._bootstrap_servers = (
            [bootstrap_servers] if isinstance(bootstrap_servers, str) else bootstrap_servers
        )
        self._parse_json = parse_json
        self._producer: _t.Optional[AIOKafkaProducer] = None

    async def _connect(self) -> None:
        """Creates and starts a Kafka producer."""
        producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        await producer.start()
        self._producer = producer

    async def _disconnect(self) -> None:
        """Stops and closes the Kafka producer."""
        if self._producer is not None:
            producer = self._producer
            self._producer = None
            await producer.stop()

    async def _send(self, messages: list[_t.Any]) -> None:
        """Sends messages to the Kafka topic.

        Args:
            messages: A list of bytes objects to send.

        Raises:
            MessageBrokerConnectionError: If the producer is not connected.
            MessageBrokerError: If a send failed or the buffer could not be flushed.
        """
        if self._producer is None:
            raise MessageBrokerConnectionError("Kafka producer is not connected")
        try:
            # `send` returns a future that resolves once the broker acknowledges the
            # record; awaiting them together keeps the producer's batching intact.
            await asyncio.gather(
                *(self._producer.send(self._topic, value=msg_data) for msg_data in messages)
            )
            await self._producer.flush()
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded bytes messages.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of bytes objects ready to send.
        """
        return encode_records_bytes(data, self._parse_json)
