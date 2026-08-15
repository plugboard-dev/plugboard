"""Unit tests for Kafka message data reader/writer."""

from __future__ import annotations

import importlib.machinery
import json
import sys
import typing as _t
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugboard.exceptions import NoMoreDataException


# ---------------------------------------------------------------------------
# Mock the aiokafka module before importing the implementation
# ---------------------------------------------------------------------------


def _make_mock_module(name: str) -> MagicMock:
    """Creates a mock module with __spec__ set for find_spec compatibility."""
    mock = MagicMock()
    mock.__spec__ = importlib.machinery.ModuleSpec(name, None)
    return mock


_mock_aiokafka = _make_mock_module("aiokafka")
_mock_consumer_class = MagicMock()
_mock_producer_class = MagicMock()
_mock_aiokafka.AIOKafkaConsumer = _mock_consumer_class
_mock_aiokafka.AIOKafkaProducer = _mock_producer_class

sys.modules.setdefault("aiokafka", _mock_aiokafka)

from plugboard.library.kafka_io import KafkaDataReader, KafkaDataWriter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kafka_record(value: dict[str, _t.Any] | bytes) -> MagicMock:
    """Creates a mock Kafka ConsumerRecord."""
    record = MagicMock()
    if isinstance(value, dict):
        record.value = json.dumps(value).encode("utf-8")
    else:
        record.value = value
    record.topic = "test-topic"
    record.partition = 0
    record.offset = 0
    return record


# ---------------------------------------------------------------------------
# Tests: KafkaDataReader
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kafka_reader_connect() -> None:
    """Tests that the reader creates and starts a Kafka consumer."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x", "y"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
    )
    await reader._connect()

    _mock_consumer_class.assert_called()
    mock_consumer.start.assert_called()
    assert reader._consumer is mock_consumer


@pytest.mark.asyncio
async def test_kafka_reader_disconnect() -> None:
    """Tests that the reader stops the Kafka consumer."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
    )
    await reader._connect()
    await reader._disconnect()

    mock_consumer.stop.assert_called()
    assert reader._consumer is None


@pytest.mark.asyncio
async def test_kafka_reader_receive() -> None:
    """Tests receiving messages from Kafka."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()

    test_data = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]
    mock_records = [_make_kafka_record(d) for d in test_data]
    tp = MagicMock()
    mock_consumer.getmany = AsyncMock(return_value={tp: mock_records})

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x", "y"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
        chunk_size=10,
    )
    await reader._connect()
    messages = await reader._receive()

    assert len(messages) == 2
    mock_consumer.getmany.assert_called()


@pytest.mark.asyncio
async def test_kafka_reader_receive_empty() -> None:
    """Tests that empty response raises NoMoreDataException."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()
    mock_consumer.getmany = AsyncMock(return_value={})

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
    )
    await reader._connect()

    with pytest.raises(NoMoreDataException):
        await reader._receive()


@pytest.mark.asyncio
async def test_kafka_reader_convert_json() -> None:
    """Tests converting JSON Kafka messages to field buffer."""
    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x", "y"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
        parse_json=True,
    )

    mock_records = [
        _make_kafka_record({"x": 1, "y": "a"}),
        _make_kafka_record({"x": 2, "y": "b"}),
    ]
    result = await reader._convert(mock_records)
    assert list(result["x"]) == [1, 2]
    assert list(result["y"]) == ["a", "b"]


@pytest.mark.asyncio
async def test_kafka_reader_convert_raw() -> None:
    """Tests converting raw Kafka messages to field buffer."""
    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["data"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
        parse_json=False,
    )

    mock_records = [_make_kafka_record(b"raw-1"), _make_kafka_record(b"raw-2")]
    result = await reader._convert(mock_records)
    assert list(result["data"]) == ["raw-1", "raw-2"]


@pytest.mark.asyncio
async def test_kafka_reader_ack() -> None:
    """Tests committing offsets for Kafka messages."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()
    mock_consumer.commit = AsyncMock()

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
    )
    await reader._connect()

    mock_records = [_make_kafka_record({"x": 1})]
    await reader._ack(mock_records)

    mock_consumer.commit.assert_called()


@pytest.mark.asyncio
async def test_kafka_reader_bootstrap_servers_list() -> None:
    """Tests that bootstrap_servers can be a list."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers=["host1:9092", "host2:9092"],
        group_id="test-group",
    )
    await reader._connect()

    call_kwargs = _mock_consumer_class.call_args[1]
    assert call_kwargs["bootstrap_servers"] == ["host1:9092", "host2:9092"]


@pytest.mark.asyncio
async def test_kafka_reader_bootstrap_servers_string() -> None:
    """Tests that bootstrap_servers string is converted to list."""
    mock_consumer = AsyncMock()
    _mock_consumer_class.return_value = mock_consumer
    mock_consumer.start = AsyncMock()

    reader = KafkaDataReader(
        name="test-kafka-reader",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        group_id="test-group",
    )
    await reader._connect()

    call_kwargs = _mock_consumer_class.call_args[1]
    assert call_kwargs["bootstrap_servers"] == ["localhost:9092"]


# ---------------------------------------------------------------------------
# Tests: KafkaDataWriter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kafka_writer_connect() -> None:
    """Tests that the writer creates and starts a Kafka producer."""
    mock_producer = AsyncMock()
    _mock_producer_class.return_value = mock_producer
    mock_producer.start = AsyncMock()

    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
    )
    await writer._connect()

    _mock_producer_class.assert_called()
    mock_producer.start.assert_called()
    assert writer._producer is mock_producer


@pytest.mark.asyncio
async def test_kafka_writer_disconnect() -> None:
    """Tests that the writer stops the Kafka producer."""
    mock_producer = AsyncMock()
    _mock_producer_class.return_value = mock_producer
    mock_producer.start = AsyncMock()
    mock_producer.stop = AsyncMock()

    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
    )
    await writer._connect()
    await writer._disconnect()

    mock_producer.stop.assert_called()
    assert writer._producer is None


@pytest.mark.asyncio
async def test_kafka_writer_send() -> None:
    """Tests sending messages to Kafka."""
    mock_producer = AsyncMock()
    _mock_producer_class.return_value = mock_producer
    mock_producer.start = AsyncMock()
    mock_producer.send_and_wait = AsyncMock()

    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
    )
    await writer._connect()

    messages = [b"msg1", b"msg2"]
    await writer._send(messages)

    assert mock_producer.send_and_wait.call_count == 2


@pytest.mark.asyncio
async def test_kafka_writer_convert_json() -> None:
    """Tests converting field data to JSON messages."""
    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["x", "y"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        parse_json=True,
    )

    data = {"x": deque([1, 2]), "y": deque(["a", "b"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert json.loads(messages[0]) == {"x": 1, "y": "a"}
    assert json.loads(messages[1]) == {"x": 2, "y": "b"}


@pytest.mark.asyncio
async def test_kafka_writer_convert_raw() -> None:
    """Tests converting field data to raw bytes messages."""
    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["data"],
        topic="test-topic",
        bootstrap_servers="localhost:9092",
        parse_json=False,
    )

    data = {"data": deque([b"raw1", b"raw2"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert messages[0] == b"raw1"
    assert messages[1] == b"raw2"


@pytest.mark.asyncio
async def test_kafka_writer_bootstrap_servers_list() -> None:
    """Tests that bootstrap_servers can be a list."""
    mock_producer = AsyncMock()
    _mock_producer_class.return_value = mock_producer
    mock_producer.start = AsyncMock()

    writer = KafkaDataWriter(
        name="test-kafka-writer",
        field_names=["x"],
        topic="test-topic",
        bootstrap_servers=["host1:9092", "host2:9092"],
    )
    await writer._connect()

    call_kwargs = _mock_producer_class.call_args[1]
    assert call_kwargs["bootstrap_servers"] == ["host1:9092", "host2:9092"]
