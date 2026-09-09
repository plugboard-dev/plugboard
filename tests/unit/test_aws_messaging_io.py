"""Unit tests for AWS SQS/SNS message data reader/writer."""

from __future__ import annotations

from collections import deque
import importlib.machinery
import json
import sys
import typing as _t
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Mock the aioboto3 module before importing the implementation
# ---------------------------------------------------------------------------


def _make_mock_module(name: str) -> MagicMock:
    """Creates a mock module with __spec__ set for find_spec compatibility."""
    mock = MagicMock()
    mock.__spec__ = importlib.machinery.ModuleSpec(name, None)
    return mock


_mock_aioboto3 = _make_mock_module("aioboto3")
_mock_aioboto3_session = MagicMock()
_mock_aioboto3.Session.return_value = _mock_aioboto3_session

sys.modules.setdefault("aioboto3", _mock_aioboto3)

from plugboard.library.aws_messaging_io import AWSSNSDataWriter, AWSSQSDataReader  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sqs_message(body: dict[str, _t.Any] | str) -> dict[str, _t.Any]:
    """Creates a mock SQS message dict."""
    if isinstance(body, dict):
        body_str = json.dumps(body)
    else:
        body_str = body
    return {
        "MessageId": f"msg-{id(body)}",
        "ReceiptHandle": f"receipt-{id(body)}",
        "Body": body_str,
    }


def _setup_mock_client() -> tuple[AsyncMock, AsyncMock]:
    """Sets up a mock boto3 client with async context manager."""
    mock_client = AsyncMock()
    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=None)
    _mock_aioboto3_session.client.return_value = mock_client_ctx
    return mock_client, mock_client_ctx


# ---------------------------------------------------------------------------
# Tests: AWSSQSDataReader
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aws_sqs_reader_connect() -> None:
    """Tests that the reader creates an SQS client on connect."""
    mock_client, _ = _setup_mock_client()

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x", "y"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
    )
    await reader._connect()

    _mock_aioboto3_session.client.assert_called_with("sqs", region_name="us-east-1")
    assert reader._client is mock_client


@pytest.mark.asyncio
async def test_aws_sqs_reader_disconnect() -> None:
    """Tests that the reader closes the SQS client on disconnect."""
    mock_client, mock_client_ctx = _setup_mock_client()

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
    )
    await reader._connect()
    await reader._disconnect()

    mock_client_ctx.__aexit__.assert_called_once()
    assert reader._client is None


@pytest.mark.asyncio
async def test_aws_sqs_reader_receive() -> None:
    """Tests receiving messages from SQS."""
    mock_client, _ = _setup_mock_client()

    test_data = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]
    sqs_messages = [_make_sqs_message(d) for d in test_data]
    mock_client.receive_message = AsyncMock(return_value={"Messages": sqs_messages})

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x", "y"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
        chunk_size=10,
    )
    await reader._connect()
    messages = await reader._receive()

    assert len(messages) == 2
    mock_client.receive_message.assert_called()


@pytest.mark.asyncio
async def test_aws_sqs_reader_receive_empty() -> None:
    """Tests receiving empty response from SQS."""
    mock_client, _ = _setup_mock_client()
    mock_client.receive_message = AsyncMock(return_value={})

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
    )
    await reader._connect()
    messages = await reader._receive()

    assert messages == []


@pytest.mark.asyncio
async def test_aws_sqs_reader_convert_json() -> None:
    """Tests converting JSON SQS messages to field buffer."""
    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x", "y"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
        parse_json=True,
    )

    sqs_messages = [
        _make_sqs_message({"x": 1, "y": "a"}),
        _make_sqs_message({"x": 2, "y": "b"}),
    ]
    result = await reader._convert(sqs_messages)
    assert list(result["x"]) == [1, 2]
    assert list(result["y"]) == ["a", "b"]


@pytest.mark.asyncio
async def test_aws_sqs_reader_convert_raw() -> None:
    """Tests converting raw SQS messages to field buffer."""
    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["data"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
        parse_json=False,
    )

    sqs_messages = [_make_sqs_message("raw-data-1"), _make_sqs_message("raw-data-2")]
    result = await reader._convert(sqs_messages)
    assert list(result["data"]) == ["raw-data-1", "raw-data-2"]


@pytest.mark.asyncio
async def test_aws_sqs_reader_ack() -> None:
    """Tests acknowledging (deleting) SQS messages."""
    mock_client, _ = _setup_mock_client()
    mock_client.delete_message = AsyncMock()

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
    )
    await reader._connect()

    sqs_messages = [_make_sqs_message({"x": 1})]
    await reader._ack(sqs_messages)

    mock_client.delete_message.assert_called()


@pytest.mark.asyncio
async def test_aws_sqs_reader_long_polling() -> None:
    """Tests that long polling is configured correctly."""
    mock_client, _ = _setup_mock_client()
    mock_client.receive_message = AsyncMock(return_value={})

    reader = AWSSQSDataReader(
        name="test-sqs-reader",
        field_names=["x"],
        topic="test-queue",
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        region="us-east-1",
        wait_time_seconds=15,
    )
    await reader._connect()
    await reader._receive()

    call_args = mock_client.receive_message.call_args
    assert call_args[1]["WaitTimeSeconds"] == 15


# ---------------------------------------------------------------------------
# Tests: AWSSNSDataWriter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aws_sns_writer_connect() -> None:
    """Tests that the writer creates an SNS client on connect."""
    mock_client, _ = _setup_mock_client()

    writer = AWSSNSDataWriter(
        name="test-sns-writer",
        field_names=["x"],
        topic="test-topic",
        topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        region="us-east-1",
    )
    await writer._connect()

    _mock_aioboto3_session.client.assert_called_with("sns", region_name="us-east-1")
    assert writer._client is mock_client


@pytest.mark.asyncio
async def test_aws_sns_writer_disconnect() -> None:
    """Tests that the writer closes the SNS client on disconnect."""
    mock_client, mock_client_ctx = _setup_mock_client()

    writer = AWSSNSDataWriter(
        name="test-sns-writer",
        field_names=["x"],
        topic="test-topic",
        topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        region="us-east-1",
    )
    await writer._connect()
    await writer._disconnect()

    mock_client_ctx.__aexit__.assert_called()
    assert writer._client is None


@pytest.mark.asyncio
async def test_aws_sns_writer_send() -> None:
    """Tests sending messages to SNS."""
    mock_client, _ = _setup_mock_client()
    mock_client.publish = AsyncMock()

    writer = AWSSNSDataWriter(
        name="test-sns-writer",
        field_names=["x"],
        topic="test-topic",
        topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        region="us-east-1",
    )
    await writer._connect()

    messages = ['{"x": 1}', '{"x": 2}']
    await writer._send(messages)

    assert mock_client.publish.call_count == 2


@pytest.mark.asyncio
async def test_aws_sns_writer_convert_json() -> None:
    """Tests converting field data to JSON messages."""
    writer = AWSSNSDataWriter(
        name="test-sns-writer",
        field_names=["x", "y"],
        topic="test-topic",
        topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        region="us-east-1",
        parse_json=True,
    )

    data = {"x": deque([1, 2]), "y": deque(["a", "b"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert json.loads(messages[0]) == {"x": 1, "y": "a"}
    assert json.loads(messages[1]) == {"x": 2, "y": "b"}


@pytest.mark.asyncio
async def test_aws_sns_writer_convert_raw() -> None:
    """Tests converting field data to raw string messages."""
    writer = AWSSNSDataWriter(
        name="test-sns-writer",
        field_names=["data"],
        topic="test-topic",
        topic_arn="arn:aws:sns:us-east-1:123456789:test-topic",
        region="us-east-1",
        parse_json=False,
    )

    data = {"data": deque(["raw1", "raw2"])}
    messages = await writer._convert(data)

    assert len(messages) == 2
    assert messages[0] == "raw1"
    assert messages[1] == "raw2"
