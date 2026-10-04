"""Unit tests for the Apache Kafka message data implementations."""

from __future__ import annotations

from collections import deque
import typing as _t
from unittest.mock import AsyncMock, MagicMock, call

from aiokafka.errors import (
    KafkaConnectionError,
    RecordTooLargeError,
    TopicAuthorizationFailedError,
)
from aiokafka.structs import OffsetAndMetadata, TopicPartition
import pytest

from plugboard.exceptions import (
    MessageBrokerConnectionError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
)
from plugboard.library import kafka_io
from plugboard.library.kafka_io import KafkaDataReader, KafkaDataWriter
from plugboard.utils.settings import Settings
from tests import conftest


def consumer_record(topic: str, partition: int, offset: int, value: bytes) -> MagicMock:
    """Builds a Kafka `ConsumerRecord` double."""
    record = MagicMock(name="consumer_record")
    record.topic = topic
    record.partition = partition
    record.offset = offset
    record.value = value
    return record


@pytest.fixture
def consumer(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces `AIOKafkaConsumer` with a double that records its construction."""
    client = MagicMock(name="consumer")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.commit = AsyncMock()
    client.getmany = AsyncMock(return_value={})
    factory = MagicMock(name="AIOKafkaConsumer", return_value=client)
    monkeypatch.setattr(kafka_io, "AIOKafkaConsumer", factory)
    client.factory = factory
    return client


@pytest.fixture
def producer(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces `AIOKafkaProducer` with a double that records its construction."""
    client = MagicMock(name="producer")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.send = AsyncMock()
    client.flush = AsyncMock()
    client.send_and_wait = AsyncMock()
    factory = MagicMock(name="AIOKafkaProducer", return_value=client)
    monkeypatch.setattr(kafka_io, "AIOKafkaProducer", factory)
    client.factory = factory
    return client


def make_reader(**kwargs: _t.Any) -> KafkaDataReader:
    """Builds a reader for the fixed test topic/group."""
    kwargs.setdefault("field_names", ["x", "y"])
    return KafkaDataReader(
        name="kafka-reader",
        topic="test-topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        **kwargs,
    )


def make_writer(**kwargs: _t.Any) -> KafkaDataWriter:
    """Builds a writer for the fixed test topic."""
    kwargs.setdefault("field_names", ["x", "y"])
    return KafkaDataWriter(
        name="kafka-writer",
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Reader: connection and consuming
# ---------------------------------------------------------------------------


async def test_reader_starts_consumer_on_topic_group(consumer: MagicMock) -> None:
    """Tests the consumer is built for the topic, group and batch size."""
    reader = make_reader(chunk_size=5)
    await reader._connect()

    consumer.factory.assert_called_once_with(
        "test-topic",
        bootstrap_servers=["localhost:9092"],
        group_id="test-group",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=5,
    )
    consumer.start.assert_awaited_once_with()


async def test_reader_stops_consumer_on_disconnect(consumer: MagicMock) -> None:
    """Tests that teardown stops the consumer, releasing its group membership."""
    reader = make_reader()
    await reader._connect()
    await reader._disconnect()
    consumer.stop.assert_awaited_once_with()


async def test_reader_flattens_records_from_partitions(consumer: MagicMock) -> None:
    """Tests that records from every assigned partition are returned."""
    consumer.getmany.return_value = {
        TopicPartition("test-topic", 0): [consumer_record("test-topic", 0, 1, b"{}")],
        TopicPartition("test-topic", 1): [
            consumer_record("test-topic", 1, 7, b"{}"),
            consumer_record("test-topic", 1, 8, b"{}"),
        ],
    }
    reader = make_reader()
    await reader._connect()

    messages = await reader._receive()

    consumer.getmany.assert_awaited_once_with(timeout_ms=30_000, max_records=10)
    assert [(r.partition, r.offset) for r in messages] == [(0, 1), (1, 7), (1, 8)]


async def test_reader_empty_poll_returns_no_messages(consumer: MagicMock) -> None:
    """Tests that a timed-out poll reads as 'nothing yet', not as an exhausted topic.

    A consumer catching up between messages must keep running, so an empty poll must
    not raise `NoMoreDataException`.
    """
    consumer.getmany.return_value = {}
    reader = make_reader()
    await reader._connect()
    assert await reader._receive() == []


async def test_reader_converts_json_values(consumer: MagicMock) -> None:
    """Tests that JSON record values become field buffers."""
    reader = make_reader()
    await reader._connect()
    batch = [
        consumer_record("test-topic", 0, 1, b'{"x": 1, "y": "a"}'),
        consumer_record("test-topic", 0, 2, b'{"x": 2, "y": "b"}'),
    ]
    assert await reader._convert(batch) == {"x": deque([1, 2]), "y": deque(["a", "b"])}


async def test_reader_non_json_value_uses_data_field(consumer: MagicMock) -> None:
    """Tests that a raw value is exposed through the `data` field."""
    reader = make_reader(field_names=["data"], parse_json=False)
    await reader._connect()
    converted = await reader._convert([consumer_record("test-topic", 0, 1, b"hello")])
    assert converted == {"data": deque(["hello"])}


# ---------------------------------------------------------------------------
# Reader: offset commits
# ---------------------------------------------------------------------------


async def test_reader_commits_offsets_of_processed_records(consumer: MagicMock) -> None:
    """Tests that an ack commits the offset *after* each processed record.

    Committing the consumer position instead of these offsets would mark records that
    were never processed as done, and they would never be redelivered.
    """
    reader = make_reader()
    await reader._connect()
    records = [
        consumer_record("test-topic", 0, 3, b"{}"),
        consumer_record("test-topic", 0, 4, b"{}"),
    ]

    await reader._ack(records)

    consumer.commit.assert_awaited_once_with(
        offsets={TopicPartition("test-topic", 0): OffsetAndMetadata(5, "")}
    )


async def test_reader_commits_highest_offset_per_partition(consumer: MagicMock) -> None:
    """Tests that out-of-order records commit the furthest offset for each partition."""
    reader = make_reader()
    await reader._connect()
    records = [
        consumer_record("test-topic", 1, 2, b"{}"),
        consumer_record("test-topic", 0, 10, b"{}"),
        consumer_record("test-topic", 1, 5, b"{}"),
        consumer_record("test-topic", 0, 8, b"{}"),
    ]

    await reader._ack(records)

    committed = consumer.commit.await_args.kwargs["offsets"]
    assert committed == {
        TopicPartition("test-topic", 0): OffsetAndMetadata(11, ""),
        TopicPartition("test-topic", 1): OffsetAndMetadata(6, ""),
    }


async def test_reader_commits_nothing_without_records(consumer: MagicMock) -> None:
    """Tests that an empty batch does not issue a commit."""
    reader = make_reader()
    await reader._connect()
    await reader._ack([])
    consumer.commit.assert_not_awaited()


async def test_reader_without_connection_raises_connection_error(consumer: MagicMock) -> None:
    """Tests that consuming before connecting fails loudly."""
    reader = make_reader()
    with pytest.raises(MessageBrokerConnectionError):
        await reader._receive()
    with pytest.raises(MessageBrokerConnectionError):
        await reader._ack([])


# ---------------------------------------------------------------------------
# Reader: error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TopicAuthorizationFailedError("denied"), MessageBrokerPermanentError),
        (RecordTooLargeError("too big"), MessageBrokerPermanentError),
        (KafkaConnectionError("down"), MessageBrokerTransientError),
    ],
)
async def test_reader_maps_kafka_errors(
    consumer: MagicMock, error: Exception, expected: type[Exception]
) -> None:
    """Tests that Kafka failures land on the right broker exception type."""
    consumer.getmany.side_effect = error
    reader = make_reader()
    await reader._connect()

    with pytest.raises(expected):
        await reader._receive()


async def test_reader_unclassified_error_propagates(consumer: MagicMock) -> None:
    """Tests that an unknown error is not rewritten into a broker exception."""
    consumer.getmany.side_effect = ValueError("unexpected")
    reader = make_reader()
    await reader._connect()

    with pytest.raises(ValueError, match="unexpected"):
        await reader._receive()


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


async def test_writer_starts_producer(producer: MagicMock) -> None:
    """Tests that the producer is created and started."""
    writer = make_writer()
    await writer._connect()
    producer.factory.assert_called_once_with(bootstrap_servers=["localhost:9092"])
    producer.start.assert_awaited_once_with()


async def test_writer_stops_producer_on_disconnect(producer: MagicMock) -> None:
    """Tests that teardown stops the producer."""
    writer = make_writer()
    await writer._connect()
    await writer._disconnect()
    producer.stop.assert_awaited_once_with()


async def test_writer_sends_batch_then_flushes_once(producer: MagicMock) -> None:
    """Tests that records are submitted together and the buffer flushed once.

    Awaiting each send individually (as `send_and_wait` does) costs one round trip per
    record and defeats the producer's batching.
    """
    writer = make_writer()
    await writer._connect()

    await writer._send([b"one", b"two", b"three"])

    assert producer.send.await_args_list == [
        call("test-topic", value=b"one"),
        call("test-topic", value=b"two"),
        call("test-topic", value=b"three"),
    ]
    producer.send_and_wait.assert_not_awaited()
    producer.flush.assert_awaited_once_with()


async def test_writer_converts_fields_to_json_bytes(producer: MagicMock) -> None:
    """Tests that buffered fields become one JSON message per record."""
    writer = make_writer()
    await writer._connect()
    converted = await writer._convert({"x": deque([1, 2]), "y": deque(["a", "b"])})
    assert converted == [b'{"x": 1, "y": "a"}', b'{"x": 2, "y": "b"}']


async def test_writer_non_json_sends_first_field(producer: MagicMock) -> None:
    """Tests that a raw writer publishes the first field's value."""
    writer = make_writer(field_names=["x"], parse_json=False)
    await writer._connect()
    assert await writer._convert({"x": deque(["hello"])}) == [b"hello"]


async def test_writer_send_failure_maps_error(producer: MagicMock) -> None:
    """Tests that a failed send surfaces as a broker exception."""
    producer.send.side_effect = KafkaConnectionError("down")
    writer = make_writer()
    await writer._connect()

    with pytest.raises(MessageBrokerTransientError):
        await writer._send([b"one"])


async def test_writer_without_connection_raises_connection_error(producer: MagicMock) -> None:
    """Tests that sending before connecting fails loudly."""
    writer = make_writer()
    with pytest.raises(MessageBrokerConnectionError):
        await writer._send([b"one"])


# ---------------------------------------------------------------------------
# Settings resolution
# ---------------------------------------------------------------------------


async def test_bootstrap_servers_fall_back_to_settings() -> None:
    """Tests that `KAFKA_BOOTSTRAP_SERVERS` supplies the brokers when not passed."""
    settings = Settings.model_validate({"kafka": {"bootstrap_servers": "kafka:9092"}})
    with conftest.override_settings(settings):
        writer = KafkaDataWriter(name="kafka-writer", topic="test-topic", field_names=["x"])
    assert writer._bootstrap_servers == ["kafka:9092"]


def test_bootstrap_servers_accepts_a_list() -> None:
    """Tests that an explicit list of brokers is kept as given."""
    reader = KafkaDataReader(
        name="kafka-reader",
        topic="test-topic",
        group_id="test-group",
        field_names=["x"],
        bootstrap_servers=["a:9092", "b:9092"],
    )
    assert reader._bootstrap_servers == ["a:9092", "b:9092"]


def test_missing_bootstrap_servers_names_the_environment_variable() -> None:
    """Tests that unresolvable brokers report what to configure."""
    with conftest.override_settings(Settings.model_validate({})):
        with pytest.raises(ValueError, match="KAFKA_BOOTSTRAP_SERVERS"):
            KafkaDataWriter(
                name="kafka-writer",
                topic="test-topic",
                field_names=["x"],
                bootstrap_servers=None,
            )
