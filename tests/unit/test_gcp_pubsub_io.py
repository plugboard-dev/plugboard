"""Unit tests for the Google Cloud PubSub message data implementations."""

from __future__ import annotations

from collections import deque
import threading
from types import SimpleNamespace
import typing as _t
from unittest.mock import MagicMock, call

from google.api_core import exceptions as gcp_exceptions
import pytest

from plugboard.exceptions import (
    MessageBrokerConnectionError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
    NoMoreDataException,
)
from plugboard.library import gcp_pubsub_io
from plugboard.library.gcp_pubsub_io import GCPPubSubDataReader, GCPPubSubDataWriter
from plugboard.utils.settings import Settings
from tests import conftest


def make_message(data: bytes) -> MagicMock:
    """Builds a PubSub `ReceivedMessage` double carrying `data`."""
    wrapper = MagicMock()
    wrapper.message.data = data
    wrapper.ack_id = f"ack-{data!r}"
    return wrapper


@pytest.fixture
def subscriber(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces the PubSub subscriber client class with a per-test double.

    The double is synchronous, so any call it records also proves the implementation
    left the event loop thread.
    """
    client = MagicMock(name="subscriber_client")
    client.pull.return_value = MagicMock(received_messages=[])
    factory = MagicMock(name="SubscriberClient", return_value=client)
    monkeypatch.setattr(
        gcp_pubsub_io,
        "pubsub_v1",
        SimpleNamespace(SubscriberClient=factory, PublisherClient=MagicMock()),
    )
    return client


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces the PubSub publisher client class with a per-test double."""
    client = MagicMock(name="publisher_client")
    factory = MagicMock(name="PublisherClient", return_value=client)
    monkeypatch.setattr(
        gcp_pubsub_io,
        "pubsub_v1",
        SimpleNamespace(SubscriberClient=MagicMock(), PublisherClient=factory),
    )
    return client


def make_reader(**kwargs: _t.Any) -> GCPPubSubDataReader:
    """Builds a reader for the fixed test project/subscription."""
    kwargs.setdefault("field_names", ["x", "y"])
    return GCPPubSubDataReader(
        name="gcp-reader",
        project_id="test-project",
        subscription_id="test-subscription",
        **kwargs,
    )


def make_writer(**kwargs: _t.Any) -> GCPPubSubDataWriter:
    """Builds a writer for the fixed test project/topic."""
    kwargs.setdefault("field_names", ["x", "y"])
    return GCPPubSubDataWriter(
        name="gcp-writer",
        project_id="test-project",
        topic_id="test-topic",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


async def test_reader_connect_builds_client_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests that constructing the subscriber client does not run on the event loop.

    Building the client opens a gRPC channel and starts its threads, which is blocking.
    """
    build_threads: list[str] = []
    client = MagicMock(name="subscriber_client")

    def _build(*args: _t.Any, **kwargs: _t.Any) -> MagicMock:
        build_threads.append(threading.current_thread().name)
        return client

    monkeypatch.setattr(
        gcp_pubsub_io,
        "pubsub_v1",
        SimpleNamespace(SubscriberClient=_build, PublisherClient=MagicMock()),
    )
    reader = make_reader()
    await reader._connect()

    assert build_threads == [build_threads[0]]
    assert build_threads[0] != threading.current_thread().name


async def test_reader_pulls_from_subscription_path(subscriber: MagicMock) -> None:
    """Tests that a pull asks for the configured subscription and batch size."""
    subscriber.pull.return_value = MagicMock(received_messages=[make_message(b'{"x": 1}')])
    reader = make_reader(chunk_size=5)
    await reader._connect()

    messages = await reader._receive()

    subscriber.pull.assert_called_once_with(
        request={
            "subscription": "projects/test-project/subscriptions/test-subscription",
            "max_messages": 5,
        },
        timeout=30.0,
    )
    assert len(messages) == 1


async def test_reader_empty_pull_returns_no_messages(subscriber: MagicMock) -> None:
    """Tests that an idle pull reads as 'nothing yet', not as an exhausted source."""
    subscriber.pull.return_value = MagicMock(received_messages=[])
    reader = make_reader()
    await reader._connect()
    assert await reader._receive() == []


async def test_reader_pulls_off_the_event_loop(subscriber: MagicMock) -> None:
    """Tests that the blocking PubSub pull runs in a worker thread.

    `pull` is synchronous gRPC in the real client; if it ran on the event loop it would
    stall every other component in the process.
    """
    caller_threads: list[str] = []

    def _pull(request: dict[str, _t.Any], timeout: float) -> MagicMock:
        caller_threads.append(threading.current_thread().name)
        return MagicMock(received_messages=[])

    subscriber.pull.side_effect = _pull
    reader = make_reader()
    await reader._connect()
    await reader._receive()

    assert len(caller_threads) == 1
    assert caller_threads[0] != threading.current_thread().name


async def test_reader_converts_json_messages(subscriber: MagicMock) -> None:
    """Tests that JSON payloads become field buffers keyed by the declared fields."""
    reader = make_reader()
    await reader._connect()
    batch = [make_message(b'{"x": 1, "y": "a"}'), make_message(b'{"x": 2, "y": "b"}')]
    assert await reader._convert(batch) == {"x": deque([1, 2]), "y": deque(["a", "b"])}


async def test_reader_non_json_messages_fill_single_field() -> None:
    """Tests that a raw payload is exposed through the `data` field."""
    reader = make_reader(field_names=["data"], parse_json=False)
    await reader._connect()
    converted = await reader._convert([make_message(b"hello")])
    assert converted == {"data": deque([b"hello"])}


async def test_reader_ack_sends_ack_ids(subscriber: MagicMock) -> None:
    """Tests that acknowledging a batch sends exactly its ack ids."""
    reader = make_reader()
    await reader._connect()
    messages = [make_message(b'{"x": 1}'), make_message(b'{"x": 2}')]

    await reader._ack(messages)

    subscriber.acknowledge.assert_called_once_with(
        request={
            "subscription": "projects/test-project/subscriptions/test-subscription",
            "ack_ids": [msg.ack_id for msg in messages],
        }
    )


async def test_reader_disconnect_closes_subscriber(subscriber: MagicMock) -> None:
    """Tests that teardown closes the client, releasing its channel."""
    reader = make_reader()
    await reader._connect()
    await reader._disconnect()
    subscriber.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (gcp_exceptions.NotFound("gone"), NoMoreDataException),
        (gcp_exceptions.PermissionDenied("nope"), MessageBrokerPermanentError),
        (gcp_exceptions.InvalidArgument("bad"), MessageBrokerPermanentError),
        (gcp_exceptions.ServiceUnavailable("busy"), MessageBrokerTransientError),
        (gcp_exceptions.DeadlineExceeded("late"), MessageBrokerTransientError),
    ],
)
async def test_reader_maps_broker_errors(
    subscriber: MagicMock, error: Exception, expected: type[Exception]
) -> None:
    """Tests that PubSub failures land on the right broker exception type."""
    subscriber.pull.side_effect = error
    reader = make_reader()
    await reader._connect()

    with pytest.raises(expected):
        await reader._receive()


async def test_reader_unclassified_error_propagates(subscriber: MagicMock) -> None:
    """Tests that an unknown error is not rewritten into a broker exception."""
    subscriber.pull.side_effect = ValueError("unexpected")
    reader = make_reader()
    await reader._connect()

    with pytest.raises(ValueError, match="unexpected"):
        await reader._receive()


async def test_reader_without_connection_raises_connection_error(subscriber: MagicMock) -> None:
    """Tests that receiving before connecting fails loudly rather than silently."""
    reader = make_reader()
    with pytest.raises(MessageBrokerConnectionError):
        await reader._receive()


async def test_reader_missing_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that a missing project id reports the environment variable to set."""
    with conftest.override_settings(Settings.model_validate({})):
        with pytest.raises(ValueError, match="GCP_PUBSUB_PROJECT_ID"):
            GCPPubSubDataReader(
                name="gcp-reader",
                subscription_id="test-subscription",
                field_names=["x"],
                project_id=None,
            )


async def test_reader_project_id_from_settings() -> None:
    """Tests that `GCP_PUBSUB_PROJECT_ID` supplies the project when not passed."""
    settings = Settings.model_validate({"gcp_pubsub": {"project_id": "settings-project"}})
    with conftest.override_settings(settings):
        reader = GCPPubSubDataReader(
            name="gcp-reader",
            subscription_id="test-subscription",
            field_names=["x"],
        )
    assert reader._subscription_path == "projects/settings-project/subscriptions/test-subscription"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


async def test_writer_publishes_encoded_records(publisher: MagicMock) -> None:
    """Tests that each record is published to the topic path as JSON bytes."""
    futures = [MagicMock(), MagicMock()]
    publisher.publish.side_effect = futures
    writer = make_writer()
    await writer._connect()

    await writer._send([b'{"x": 1}', b'{"x": 2}'])

    assert [published.kwargs["data"] for published in publisher.publish.call_args_list] == [
        b'{"x": 1}',
        b'{"x": 2}',
    ]
    assert [published.args for published in publisher.publish.call_args_list] == [
        ("projects/test-project/topics/test-topic",)
    ] * 2
    assert [future.result.call_args for future in futures] == [
        call(timeout=60.0),
        call(timeout=60.0),
    ]


async def test_writer_waits_off_the_event_loop(publisher: MagicMock) -> None:
    """Tests that waiting for broker confirmation does not block the event loop."""
    caller_threads: list[str] = []

    class _Future:
        def result(self, timeout: float) -> None:
            caller_threads.append(threading.current_thread().name)

    publisher.publish.return_value = _Future()
    writer = make_writer()
    await writer._connect()
    await writer._send([b"one", b"two"])

    assert len(caller_threads) == 2
    assert all(name != threading.current_thread().name for name in caller_threads)


async def test_writer_converts_fields_to_json_bytes(publisher: MagicMock) -> None:
    """Tests that buffered fields become one JSON message per record."""
    writer = make_writer()
    await writer._connect()
    converted = await writer._convert({"x": deque([1, 2]), "y": deque(["a", "b"])})
    assert converted == [b'{"x": 1, "y": "a"}', b'{"x": 2, "y": "b"}']


async def test_writer_non_json_sends_first_field(publisher: MagicMock) -> None:
    """Tests that a raw writer publishes the first field's value."""
    writer = make_writer(field_names=["x"], parse_json=False)
    await writer._connect()
    assert await writer._convert({"x": deque(["hello"])}) == [b"hello"]


async def test_writer_disconnect_stops_publisher(publisher: MagicMock) -> None:
    """Tests that teardown stops the publisher so its channel and threads are released."""
    writer = make_writer()
    await writer._connect()
    await writer._disconnect()
    publisher.stop.assert_called_once_with()


async def test_writer_publish_failure_maps_error(publisher: MagicMock) -> None:
    """Tests that a publish failure surfaces as a broker exception."""
    publisher.publish.side_effect = gcp_exceptions.ServiceUnavailable("busy")
    writer = make_writer()
    await writer._connect()

    with pytest.raises(MessageBrokerTransientError):
        await writer._send([b"one"])


async def test_writer_without_connection_raises_connection_error(publisher: MagicMock) -> None:
    """Tests that sending before connecting fails loudly."""
    writer = make_writer()
    with pytest.raises(MessageBrokerConnectionError):
        await writer._send([b"one"])


async def test_writer_maps_unconfirmed_publish(publisher: MagicMock) -> None:
    """Tests that a future that fails on `result` is reported as a broker error."""
    future = MagicMock()
    future.result.side_effect = gcp_exceptions.FailedPrecondition("rejected")
    publisher.publish.return_value = future
    writer = make_writer()
    await writer._connect()

    with pytest.raises(MessageBrokerPermanentError):
        await writer._send([b"one"])
