"""Unit tests for the `MessageDataWriter` base class and its shared encoding helpers."""

from __future__ import annotations

from collections import deque
import typing as _t

import pytest

from plugboard.connector import AsyncioConnector
from plugboard.exceptions import (
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
)
from plugboard.library.message_writer import (
    MessageDataWriter,
    encode_records,
    encode_records_bytes,
    iter_records,
)
from plugboard.schemas import ConnectorSpec
from plugboard.utils.retry import RetryPolicy


class RecordingWriter(MessageDataWriter):
    """A `MessageDataWriter` that records what it sends and can script send failures.

    Each `_send` call consumes the next entry of `script`: an exception is raised, and
    anything else is recorded as a delivered batch. When the script runs out, sends
    succeed and are recorded.
    """

    def __init__(self, *args: _t.Any, script: list[_t.Any] | None = None, **kwargs: _t.Any) -> None:
        """Instantiates the writer.

        Args:
            *args: Positional arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
            script: The per-send outcomes to play back.
            **kwargs: Keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        super().__init__(*args, **kwargs)
        self.script = script or []
        self.sends: list[list[_t.Any]] = []
        self.attempts = 0
        self.connects = 0
        self.disconnects = 0

    async def _connect(self) -> None:
        self.connects += 1

    async def _disconnect(self) -> None:
        self.disconnects += 1

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        return list(iter_records(data))

    async def _send(self, messages: list[_t.Any]) -> None:
        outcome = self.script[self.attempts] if self.attempts < len(self.script) else None
        self.attempts += 1
        if isinstance(outcome, Exception):
            raise outcome
        self.sends.append(list(messages))


class UnreconnectableWriter(RecordingWriter):
    """A writer whose first connect succeeds and every reconnect afterwards fails."""

    async def _connect(self) -> None:
        self.connects += 1
        if self.connects > 1:
            raise OSError("broker unreachable")


def make_writer(
    field_names: list[str],
    *,
    script: list[_t.Any] | None = None,
    max_retries: int = 3,
    writer_cls: type[RecordingWriter] = RecordingWriter,
    **kwargs: _t.Any,
) -> RecordingWriter:
    """Builds a writer over the given fields."""
    return writer_cls(
        name="test-writer",
        field_names=field_names,
        topic="test-topic",
        script=script,
        retry_policy=RetryPolicy(max_retries=max_retries),
        **kwargs,
    )


async def connect_writer(writer: RecordingWriter) -> dict[str, AsyncioConnector]:
    """Connects input channels to a writer and returns them by field name."""
    connectors = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"{writer.name}.{field}")
        )
        for field in writer.io.inputs
    }
    await writer.io.connect(list(connectors.values()))
    return connectors


async def write_records(
    writer: RecordingWriter,
    channels: dict[str, AsyncioConnector],
    records: list[dict[str, _t.Any]],
) -> None:
    """Pushes records into the writer one at a time, stepping after each."""
    senders = {field: await channel.connect_send() for field, channel in channels.items()}
    for record in records:
        for field, value in record.items():
            await senders[field].send(value)
        await writer.step()


def delivered(writer: RecordingWriter) -> list[_t.Any]:
    """Flattens everything the writer sent."""
    return [record for batch in writer.sends for record in batch]


RECORDS = [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}, {"x": 3, "y": "c"}]
SINGLE = [{"x": 1}]  # For the single-field writers used by the retry tests.


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_init_connects_to_broker() -> None:
    """Tests that `init` opens the broker connection."""
    writer = make_writer(["x"])
    await writer.init()
    assert writer.connects == 1
    await writer.destroy()


async def test_destroy_disconnects() -> None:
    """Tests that `destroy` closes the broker connection."""
    writer = make_writer(["x"])
    await writer.init()
    await writer.destroy()
    assert writer.disconnects == 1


async def test_destroy_waits_for_in_flight_send() -> None:
    """Tests that a send still running at teardown completes instead of being dropped."""
    writer = make_writer(["x"])
    channels = await connect_writer(writer)
    await writer.init()
    await write_records(writer, channels, [{"x": 1}])
    await writer._save_chunk()  # Buffer one batch without waiting for it to land.
    await writer.destroy()
    assert delivered(writer) == [{"x": 1}]


@pytest.mark.parametrize("chunk_size", [1, 2, 3])
# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


async def test_records_are_sent_in_batches(chunk_size: int) -> None:
    """Tests that every record is delivered exactly once, in order."""
    writer = make_writer(["x", "y"], chunk_size=chunk_size)
    channels = await connect_writer(writer)
    await writer.init()

    await write_records(writer, channels, RECORDS)
    await writer.io.close()
    await writer.run()

    assert delivered(writer) == RECORDS
    assert all(len(batch) <= chunk_size for batch in writer.sends)


async def test_run_flushes_remaining_buffer() -> None:
    """Tests that data left under the chunk size is still sent when the run ends."""
    writer = make_writer(["x", "y"], chunk_size=10)
    channels = await connect_writer(writer)
    await writer.init()

    await write_records(writer, channels, RECORDS)
    assert writer.sends == []  # Below the chunk size: still buffered.

    await writer.io.close()
    await writer.run()
    assert delivered(writer) == RECORDS


# ---------------------------------------------------------------------------
# Retry and reconnection
# ---------------------------------------------------------------------------


async def test_transient_send_failure_reconnects_and_recovers() -> None:
    """Tests that a transient failure is retried after reconnecting."""
    writer = make_writer(["x"], script=[MessageBrokerTransientError("blip")], max_retries=3)
    channels = await connect_writer(writer)
    await writer.init()

    await write_records(writer, channels, SINGLE)
    await writer.io.close()
    await writer.run()

    assert delivered(writer) == [{"x": 1}]
    assert writer.attempts == 2  # Failed once, then succeeded.
    assert writer.connects == 2  # Initial connect plus one reconnect.
    assert writer.disconnects == 1


async def test_permanent_send_failure_is_not_retried() -> None:
    """Tests that a permanent broker error surfaces immediately."""
    writer = make_writer(
        ["x"],
        script=[MessageBrokerPermanentError("topic deleted"), None],
        max_retries=3,
    )
    channels = await connect_writer(writer)
    await writer.init()
    await write_records(writer, channels, SINGLE)

    await writer._save_chunk()
    send = writer._task
    assert send is not None
    with pytest.raises(MessageBrokerPermanentError, match="topic deleted"):
        await send

    assert writer.attempts == 1
    assert writer.connects == 1  # No reconnect attempted.
    writer._task = None  # The failed send is already inspected here.
    await writer.destroy()


async def test_retry_exhaustion_raises_last_send_error() -> None:
    """Tests that sends are bounded and the broker's own error is raised."""
    failures = [ConnectionError(f"failure {index}") for index in range(5)]
    writer = make_writer(["x"], script=failures, max_retries=2)
    channels = await connect_writer(writer)
    await writer.init()
    await write_records(writer, channels, SINGLE)

    await writer._save_chunk()
    send = writer._task
    assert send is not None
    with pytest.raises(ConnectionError, match="failure 2"):
        await send

    assert writer.attempts == 3  # Initial attempt plus two retries.
    assert writer.connects == 3  # Initial connect plus one reconnect per retry.
    writer._task = None
    await writer.destroy()


async def test_reconnect_failure_does_not_abort_retries() -> None:
    """Tests that a failing reconnect costs an attempt instead of ending the retrying."""
    writer = make_writer(
        ["x"],
        script=[ConnectionError("send failed")] * 3,
        max_retries=2,
        writer_cls=UnreconnectableWriter,
    )
    channels = await connect_writer(writer)
    await writer.init()
    await write_records(writer, channels, SINGLE)

    await writer._save_chunk()
    send = writer._task
    assert send is not None
    with pytest.raises(ConnectionError, match="send failed"):
        await send

    assert writer.attempts == 3  # Every attempt ran despite the reconnect failures.
    assert writer.connects == 3
    writer._task = None
    await writer.destroy()


# ---------------------------------------------------------------------------
# Shared record encoding helpers
# ---------------------------------------------------------------------------


def test_iter_records_yields_one_dict_per_row() -> None:
    """Tests that a field buffer becomes one record per row, in order."""
    buffer = {"x": deque([1, 2]), "y": deque(["a", "b"])}
    assert list(iter_records(buffer)) == [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]


def test_iter_records_stops_at_the_shortest_field() -> None:
    """Tests that an incomplete trailing row is not emitted."""
    buffer = {"x": deque([1, 2, 3]), "y": deque(["a"])}
    assert list(iter_records(buffer)) == [{"x": 1, "y": "a"}]


def test_iter_records_handles_empty_buffers() -> None:
    """Tests that empty buffers produce no records."""
    assert list(iter_records({})) == []
    assert list(iter_records({"x": deque()})) == []


def test_iter_records_is_linear_in_row_count() -> None:
    """Tests that many buffered rows convert in one pass, not one index per row."""
    rows = 20_000
    buffer = {"x": deque(range(rows)), "y": deque(range(rows))}
    records = list(iter_records(buffer))
    assert len(records) == rows
    assert records[-1] == {"x": rows - 1, "y": rows - 1}


@pytest.mark.parametrize(
    ("parse_json", "expected"),
    [
        (True, ['{"x": 1, "y": "a"}', '{"x": 2, "y": "b"}']),
        (False, ["1", "2"]),
    ],
)
def test_encode_records_as_text(parse_json: bool, expected: list[str]) -> None:
    """Tests text payloads, JSON-encoded or the raw first field."""
    assert encode_records({"x": deque([1, 2]), "y": deque(["a", "b"])}, parse_json) == expected


@pytest.mark.parametrize(
    ("parse_json", "expected"),
    [
        (True, [b'{"x": 1}', b'{"x": 2}']),
        (False, [b"1", b"2"]),
    ],
)
def test_encode_records_as_bytes(parse_json: bool, expected: list[bytes]) -> None:
    """Tests binary payloads, JSON-encoded or the raw first field."""
    assert encode_records_bytes({"x": deque([1, 2])}, parse_json) == expected


def test_encode_records_bytes_preserves_binary_payloads() -> None:
    """Tests that non-UTF-8 bytes survive a raw (non-JSON) payload untouched."""
    payload = bytes([0xFF, 0xFE, 0x00])
    assert encode_records_bytes({"x": deque([payload])}, parse_json=False) == [payload]
