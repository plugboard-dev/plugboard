"""Unit tests for GCP PubSub message data reader/writer."""

from __future__ import annotations

import importlib.machinery
import json
import sys
import typing as _t
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugboard.exceptions import NoMoreDataException


# ---------------------------------------------------------------------------
# Mock the google.cloud.pubsub_v1 module before importing the implementation
# ---------------------------------------------------------------------------


def _make_mock_module(name: str) -> MagicMock:
    """Creates a mock module with __spec__ set for find_spec compatibility."""
    mock = MagicMock()
    mock.__spec__ = importlib.machinery.ModuleSpec(name, None)
    return mock


_mock_pubsub = _make_mock_module("google.cloud.pubsub_v1")
_mock_pubsub.SubscriberClient = MagicMock()
_mock_pubsub.PublisherClient = MagicMock()

_mock_google = _make_mock_module("google")
_mock_google_cloud = _make_mock_module("google.cloud")
# Wire up the attribute chain so `from google.cloud import pubsub_v1` works
_mock_google_cloud.pubsub_v1 = _mock_pubsub
_mock_google.cloud = _mock_google_cloud

_mock_modules = {
    "google": _mock_google,
    "google.cloud": _mock_google_cloud,
    "google.cloud.pubsub_v1": _mock_pubsub,
    "google.cloud.pubsub_v1.subscriber": _make_mock_module("google.cloud.pubsub_v1.subscriber"),
    "google.cloud.pubsub_v1.subscriber.message": _make_mock_module(
        "google.cloud.pubsub_v1.subscriber.message"
    ),
}

# Install mocks before importing the module under test
for _mod_name, _mod in _mock_modules.items():
    sys.modules.setdefault(_mod_name, _mod)

from plugboard.library.gcp_pubsub_io import GCPPubSubDataReader, GCPPubSubDataWriter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pubsub_message(data: dict[str, _t.Any] | bytes) -> MagicMock:
    """Creates a mock PubSub ReceivedMessage."""
    if isinstance(data, dict):
        raw_data = json.dumps(data).encode("utf-8")
    else:
        raw_data = data
    msg = MagicMock()
    msg.message.data = raw_data
    msg.ack_id = f"ack-{id(msg)}"
    return msg


def _make_pull_response(messages: list[MagicMock]) -> MagicMock:
    """Creates a mock Pull response."""
    response = MagicMock()
    response.received_messages = messages
    return response


# ---------------------------------------------------------------------------
# Tests: GCPPubSubDataReader
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_connect() -> None:
    """Tests that the reader creates a subscriber client on connect."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x", "y"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
    )
    await reader._connect()

    _mock_pubsub.SubscriberClient.assert_called()
    assert reader._subscriber is mock_subscriber


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_disconnect() -> None:
    """Tests that the reader closes the subscriber client on disconnect."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
    )
    await reader._connect()
    await reader._disconnect()

    mock_subscriber.close.assert_called_once()
    assert reader._subscriber is None


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_receive() -> None:
    """Tests receiving messages from PubSub."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber

    test_data = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]
    mock_messages = [_make_pubsub_message(d) for d in test_data]
    mock_response = _make_pull_response(mock_messages)
    mock_subscriber.pull.return_value = mock_response

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x", "y"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
        chunk_size=10,
    )
    await reader._connect()
    messages = await reader._receive()

    assert len(messages) == 2
    mock_subscriber.pull.assert_called()


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_receive_empty() -> None:
    """Tests receiving empty response from PubSub."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber

    mock_response = _make_pull_response([])
    mock_subscriber.pull.return_value = mock_response

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
    )
    await reader._connect()
    messages = await reader._receive()

    assert messages == []


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_receive_not_found() -> None:
    """Tests that NOT_FOUND error raises NoMoreDataException."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber
    mock_subscriber.pull.side_effect = Exception("NOT_FOUND: Subscription deleted")

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
    )
    await reader._connect()

    with pytest.raises(NoMoreDataException):
        await reader._receive()


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_convert_json() -> None:
    """Tests converting JSON messages to field buffer."""
    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x", "y"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
        parse_json=True,
    )

    test_data = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]
    mock_messages = [_make_pubsub_message(d) for d in test_data]

    result = await reader._convert(mock_messages)
    assert list(result["x"]) == [1, 2]
    assert list(result["y"]) == ["a", "b"]


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_convert_raw() -> None:
    """Tests converting raw bytes messages to field buffer."""
    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["data"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
        parse_json=False,
    )

    mock_messages = [_make_pubsub_message(b"raw-data-1"), _make_pubsub_message(b"raw-data-2")]
    result = await reader._convert(mock_messages)
    assert list(result["data"]) == [b"raw-data-1", b"raw-data-2"]


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_ack() -> None:
    """Tests acknowledging messages."""
    mock_subscriber = MagicMock()
    _mock_pubsub.SubscriberClient.return_value = mock_subscriber

    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        subscription_id="test-sub",
    )
    await reader._connect()

    mock_messages = [_make_pubsub_message({"x": 1})]
    mock_messages[0].ack_id = "ack-123"
    await reader._ack(mock_messages)

    mock_subscriber.acknowledge.assert_called()
    call_args = mock_subscriber.acknowledge.call_args
    assert call_args[1]["request"]["ack_ids"] == ["ack-123"]


@pytest.mark.asyncio
async def test_gcp_pubsub_reader_subscription_path() -> None:
    """Tests that the subscription path is constructed correctly."""
    reader = GCPPubSubDataReader(
        name="test-gcp-reader",
        field_names=["x"],
        topic="test-topic",
        project_id="my-project",
        subscription_id="my-sub",
    )
    assert reader._subscription_path == "projects/my-project/subscriptions/my-sub"


# ---------------------------------------------------------------------------
# Tests: GCPPubSubDataWriter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_connect() -> None:
    """Tests that the writer creates a publisher client on connect."""
    mock_publisher = MagicMock()
    _mock_pubsub.PublisherClient.return_value = mock_publisher

    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        topic_id="test-topic-id",
    )
    await writer._connect()

    _mock_pubsub.PublisherClient.assert_called()
    assert writer._publisher is mock_publisher


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_disconnect() -> None:
    """Tests that the writer closes the publisher client on disconnect."""
    mock_publisher = MagicMock()
    _mock_pubsub.PublisherClient.return_value = mock_publisher

    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        topic_id="test-topic-id",
    )
    await writer._connect()
    await writer._disconnect()

    mock_publisher.close.assert_called_once()
    assert writer._publisher is None


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_send() -> None:
    """Tests sending messages to PubSub."""
    mock_publisher = MagicMock()
    _mock_pubsub.PublisherClient.return_value = mock_publisher

    mock_future = MagicMock()
    mock_publisher.publish.return_value = mock_future

    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["x"],
        topic="test-topic",
        project_id="test-project",
        topic_id="test-topic-id",
    )
    await writer._connect()

    messages = [b"msg1", b"msg2"]
    await writer._send(messages)

    assert mock_publisher.publish.call_count == 2
    assert mock_future.result.call_count == 2


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_convert_json() -> None:
    """Tests converting field data to JSON messages."""
    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["x", "y"],
        topic="test-topic",
        project_id="test-project",
        topic_id="test-topic-id",
        parse_json=True,
    )

    data = {"x": deque([1, 2]), "y": deque(["a", "b"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert json.loads(messages[0]) == {"x": 1, "y": "a"}
    assert json.loads(messages[1]) == {"x": 2, "y": "b"}


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_convert_raw() -> None:
    """Tests converting field data to raw bytes messages."""
    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["data"],
        topic="test-topic",
        project_id="test-project",
        topic_id="test-topic-id",
        parse_json=False,
    )

    data = {"data": deque([b"raw1", b"raw2"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert messages[0] == b"raw1"
    assert messages[1] == b"raw2"


@pytest.mark.asyncio
async def test_gcp_pubsub_writer_topic_path() -> None:
    """Tests that the topic path is constructed correctly."""
    writer = GCPPubSubDataWriter(
        name="test-gcp-writer",
        field_names=["x"],
        topic="test-topic",
        project_id="my-project",
        topic_id="my-topic",
    )
    assert writer._topic_path == "projects/my-project/topics/my-topic"
