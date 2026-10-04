"""Unit tests for the AWS SQS/SNS message data implementations."""

from __future__ import annotations

from collections import deque
import contextlib
import typing as _t
from unittest.mock import AsyncMock, MagicMock, call

from botocore.exceptions import BotoCoreError, ClientError
import pytest

from plugboard.exceptions import (
    MessageBrokerConnectionError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
    NoMoreDataException,
)
from plugboard.library import aws_messaging_io
from plugboard.library.aws_messaging_io import AWSSNSDataWriter, AWSSQSDataReader
from plugboard.utils.settings import Settings
from tests import conftest


def client_error(code: str, operation: str = "ReceiveMessage") -> ClientError:
    """Builds a botocore `ClientError` carrying the given AWS error code."""
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


@contextlib.asynccontextmanager
async def _managed(client: MagicMock, closed: list[str]) -> _t.AsyncIterator[MagicMock]:
    """Yields `client` and records that its context was exited."""
    try:
        yield client
    finally:
        closed.append(getattr(client, "service_name", "client"))


@pytest.fixture
def aws_client(monkeypatch: pytest.MonkeyPatch) -> _t.Iterator[MagicMock]:
    """Replaces the aiobotocore session with one handing out a single client double.

    The double's operations are `AsyncMock`s, so the call arguments are the observable
    behaviour of the implementation.
    """
    client = MagicMock(name="aws_client")
    client.receive_message = AsyncMock(return_value={})
    client.delete_message_batch = AsyncMock(return_value={})
    client.publish = AsyncMock(return_value={"MessageId": "m1"})
    closed: list[str] = []
    created: list[tuple[str, dict[str, _t.Any]]] = []

    def _create_client(service_name: str, **kwargs: _t.Any) -> _t.Any:
        created.append((service_name, kwargs))
        client.service_name = service_name
        return _managed(client, closed)

    session = MagicMock(name="session")
    session.create_client.side_effect = _create_client
    monkeypatch.setattr(aws_messaging_io, "get_session", lambda: session)
    client.created = created
    client.closed = closed
    yield client


def make_reader(**kwargs: _t.Any) -> AWSSQSDataReader:
    """Builds a reader for the fixed test queue."""
    kwargs.setdefault("field_names", ["x", "y"])
    return AWSSQSDataReader(
        name="sqs-reader",
        queue_url="https://sqs.test/1/messages",
        region="eu-west-1",
        **kwargs,
    )


def make_writer(**kwargs: _t.Any) -> AWSSNSDataWriter:
    """Builds a writer for the fixed test topic."""
    kwargs.setdefault("field_names", ["x", "y"])
    return AWSSNSDataWriter(
        name="sns-writer",
        topic_arn="arn:aws:sns:eu-west-1:1:messages",
        region="eu-west-1",
        **kwargs,
    )


def sqs_message(body: str, handle: str) -> dict[str, str]:
    """Builds an SQS message dict as returned by `ReceiveMessage`."""
    return {"Body": body, "ReceiptHandle": handle, "MessageId": handle}


# ---------------------------------------------------------------------------
# Reader: connection and receiving
# ---------------------------------------------------------------------------


async def test_reader_connects_sqs_client_in_region(aws_client: MagicMock) -> None:
    """Tests that the client is created for SQS in the configured region."""
    reader = make_reader()
    await reader._connect()
    assert aws_client.created == [("sqs", {"region_name": "eu-west-1"})]


async def test_reader_disconnect_exits_client_context(aws_client: MagicMock) -> None:
    """Tests that teardown closes the client rather than dropping the reference."""
    reader = make_reader()
    await reader._connect()
    await reader._disconnect()
    assert aws_client.closed == ["sqs"]


async def test_reader_receives_with_long_polling(aws_client: MagicMock) -> None:
    """Tests the receive request carries the queue, batch size and wait time."""
    aws_client.receive_message.return_value = {"Messages": [sqs_message('{"x": 1}', "h1")]}
    reader = make_reader(chunk_size=5, wait_time_seconds=7)
    await reader._connect()

    messages = await reader._receive()

    aws_client.receive_message.assert_awaited_once_with(
        QueueUrl="https://sqs.test/1/messages", MaxNumberOfMessages=5, WaitTimeSeconds=7
    )
    assert [msg["ReceiptHandle"] for msg in messages] == ["h1"]


async def test_reader_caps_batch_at_the_sqs_maximum(aws_client: MagicMock) -> None:
    """Tests that a larger `chunk_size` is capped, since SQS delivers at most 10."""
    reader = make_reader(chunk_size=25)
    await reader._connect()
    await reader._receive()
    assert aws_client.receive_message.await_args.kwargs["MaxNumberOfMessages"] == 10


def test_reader_warns_when_capping_chunk_size(capsys: pytest.CaptureFixture[str]) -> None:
    """Tests that capping `chunk_size` is reported rather than applied silently."""
    make_reader(chunk_size=25)
    assert "chunk_size is capped" in capsys.readouterr().out


async def test_reader_empty_poll_returns_no_messages(aws_client: MagicMock) -> None:
    """Tests that an empty long poll reads as 'nothing yet', not as an exhausted queue."""
    aws_client.receive_message.return_value = {}
    reader = make_reader()
    await reader._connect()
    assert await reader._receive() == []


# ---------------------------------------------------------------------------
# Reader: conversion and acknowledgment
# ---------------------------------------------------------------------------


async def test_reader_converts_json_bodies() -> None:
    """Tests that JSON message bodies become field buffers."""
    reader = make_reader()
    await reader._connect()
    batch = [sqs_message('{"x": 1, "y": "a"}', "h1"), sqs_message('{"x": 2, "y": "b"}', "h2")]
    assert await reader._convert(batch) == {"x": deque([1, 2]), "y": deque(["a", "b"])}


async def test_reader_non_json_body_uses_data_field() -> None:
    """Tests that a raw body is exposed through the `data` field."""
    reader = make_reader(field_names=["data"], parse_json=False)
    await reader._connect()
    converted = await reader._convert([sqs_message("hello", "h1")])
    assert converted == {"data": deque(["hello"])}


async def test_reader_deletes_processed_messages(aws_client: MagicMock) -> None:
    """Tests that acking deletes by receipt handle, in one batch."""
    reader = make_reader()
    await reader._connect()
    messages = [sqs_message('{"x": 1}', "h1"), sqs_message('{"x": 2}', "h2")]

    await reader._ack(messages)

    aws_client.delete_message_batch.assert_awaited_once_with(
        QueueUrl="https://sqs.test/1/messages",
        DeleteMessageRequests=[
            {"Id": "0", "ReceiptHandle": "h1"},
            {"Id": "1", "ReceiptHandle": "h2"},
        ],
    )


async def test_reader_splits_deletes_into_batch_size_chunks(aws_client: MagicMock) -> None:
    """Tests that more than 10 messages are deleted over several batch calls."""
    reader = make_reader()
    await reader._connect()
    messages = [sqs_message('{"x": 1}', f"h{index}") for index in range(12)]

    await reader._ack(messages)

    calls = aws_client.delete_message_batch.await_args_list
    assert [len(call.kwargs["DeleteMessageRequests"]) for call in calls] == [10, 2]
    assert calls[1].kwargs["DeleteMessageRequests"][0]["ReceiptHandle"] == "h10"


async def test_reader_skips_messages_without_receipt_handle(aws_client: MagicMock) -> None:
    """Tests that a message with no receipt handle is not sent to the delete API."""
    reader = make_reader()
    await reader._connect()
    await reader._ack([{"Body": '{"x": 1}'}])
    aws_client.delete_message_batch.assert_not_awaited()


async def test_reader_reports_failed_deletes_as_transient(aws_client: MagicMock) -> None:
    """Tests that a partially failed delete retries instead of claiming success."""
    aws_client.delete_message_batch.return_value = {
        "Errors": [{"Id": "0", "Code": "ReceiptHandleIsInvalid"}]
    }
    reader = make_reader()
    await reader._connect()

    with pytest.raises(MessageBrokerTransientError, match="Failed to delete 1"):
        await reader._ack([sqs_message('{"x": 1}', "h1")])


async def test_reader_without_connection_raises_connection_error(aws_client: MagicMock) -> None:
    """Tests that receiving before connecting fails loudly."""
    reader = make_reader()
    with pytest.raises(MessageBrokerConnectionError):
        await reader._receive()


# ---------------------------------------------------------------------------
# Reader: error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AWS.SimpleQueueService.NonExistentQueue", NoMoreDataException),
        ("AccessDenied", MessageBrokerPermanentError),
        ("InvalidAddress", MessageBrokerPermanentError),
        ("ThrottlingException", MessageBrokerTransientError),
        ("InternalError", MessageBrokerTransientError),
    ],
)
async def test_reader_maps_aws_error_codes(
    aws_client: MagicMock, code: str, expected: type[Exception]
) -> None:
    """Tests that AWS error codes land on the right broker exception type."""
    aws_client.receive_message.side_effect = client_error(code)
    reader = make_reader()
    await reader._connect()

    with pytest.raises(expected):
        await reader._receive()


async def test_reader_transport_error_is_transient(aws_client: MagicMock) -> None:
    """Tests that a connection-level failure is retryable."""
    aws_client.receive_message.side_effect = BotoCoreError()
    reader = make_reader()
    await reader._connect()

    with pytest.raises(MessageBrokerTransientError):
        await reader._receive()


async def test_reader_unclassified_error_propagates(aws_client: MagicMock) -> None:
    """Tests that an unknown error is not rewritten into a broker exception."""
    aws_client.receive_message.side_effect = ValueError("unexpected")
    reader = make_reader()
    await reader._connect()

    with pytest.raises(ValueError, match="unexpected"):
        await reader._receive()


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


async def test_writer_connects_sns_client(aws_client: MagicMock) -> None:
    """Tests that the writer creates a client for SNS in the configured region."""
    writer = make_writer()
    await writer._connect()
    assert aws_client.created == [("sns", {"region_name": "eu-west-1"})]


async def test_writer_publishes_each_message(aws_client: MagicMock) -> None:
    """Tests that every encoded record is published to the topic."""
    writer = make_writer()
    await writer._connect()

    await writer._send(['{"x": 1}', '{"x": 2}'])

    assert aws_client.publish.await_args_list == [
        call(TopicArn="arn:aws:sns:eu-west-1:1:messages", Message='{"x": 1}'),
        call(TopicArn="arn:aws:sns:eu-west-1:1:messages", Message='{"x": 2}'),
    ]


async def test_writer_converts_fields_to_json_strings() -> None:
    """Tests that buffered fields become one JSON message per record."""
    writer = make_writer()
    await writer._connect()
    converted = await writer._convert({"x": deque([1, 2]), "y": deque(["a", "b"])})
    assert converted == ['{"x": 1, "y": "a"}', '{"x": 2, "y": "b"}']


async def test_writer_non_json_sends_first_field() -> None:
    """Tests that a raw writer publishes the first field's value."""
    writer = make_writer(field_names=["x"], parse_json=False)
    await writer._connect()
    assert await writer._convert({"x": deque([7])}) == ["7"]


async def test_writer_missing_topic_is_permanent(aws_client: MagicMock) -> None:
    """Tests that a deleted topic is not treated as an exhausted source."""
    aws_client.publish.side_effect = client_error("NotFound", "Publish")
    writer = make_writer()
    await writer._connect()

    with pytest.raises(MessageBrokerPermanentError):
        await writer._send(['{"x": 1}'])


async def test_writer_disconnect_exits_client_context(aws_client: MagicMock) -> None:
    """Tests that teardown closes the client."""
    writer = make_writer()
    await writer._connect()
    await writer._disconnect()
    assert aws_client.closed == ["sns"]


async def test_writer_without_connection_raises_connection_error(aws_client: MagicMock) -> None:
    """Tests that sending before connecting fails loudly."""
    writer = make_writer()
    with pytest.raises(MessageBrokerConnectionError):
        await writer._send(["one"])


# ---------------------------------------------------------------------------
# Settings resolution
# ---------------------------------------------------------------------------


async def test_region_falls_back_to_settings() -> None:
    """Tests that `AWS_REGION` supplies the region when none is passed."""
    settings = Settings.model_validate({"aws": {"region": "ap-south-1"}})
    with conftest.override_settings(settings):
        reader = AWSSQSDataReader(
            name="sqs-reader", queue_url="https://sqs.test/1/messages", field_names=["x"]
        )
    assert reader._region == "ap-south-1"


def test_explicit_region_wins_over_settings() -> None:
    """Tests that an explicit region is not overridden by configuration."""
    settings = Settings.model_validate({"aws": {"region": "ap-south-1"}})
    with conftest.override_settings(settings):
        reader = AWSSQSDataReader(
            name="sqs-reader",
            queue_url="https://sqs.test/1/messages",
            field_names=["x"],
            region="us-west-2",
        )
    assert reader._region == "us-west-2"


def test_missing_region_names_the_environment_variable() -> None:
    """Tests that an unresolvable region reports what to configure."""
    with conftest.override_settings(Settings.model_validate({})):
        with pytest.raises(ValueError, match="AWS_REGION"):
            AWSSQSDataReader(
                name="sqs-reader",
                queue_url="https://sqs.test/1/messages",
                field_names=["x"],
                region=None,
            )


def test_reader_topic_defaults_to_queue_url() -> None:
    """Tests that the queue URL identifies the reader's topic."""
    reader = make_reader()
    assert reader._topic == "https://sqs.test/1/messages"


def test_writer_topic_defaults_to_topic_arn() -> None:
    """Tests that the topic ARN identifies the writer's topic."""
    writer = make_writer()
    assert writer._topic == "arn:aws:sns:eu-west-1:1:messages"
