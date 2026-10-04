"""Unit tests for the `MessageDataReader` base class."""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
import typing as _t

import pytest

from plugboard.exceptions import (
    IOStreamClosedError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
    NoMoreDataException,
)
from plugboard.library.message_reader import MessageDataReader
from plugboard.utils import retry as retry_utils
from plugboard.utils.retry import RetryPolicy


class ScriptedReader(MessageDataReader):
    """A `MessageDataReader` driven by a script of poll outcomes.

    Each `_receive` call consumes the next entry of `script`: a list of records is
    delivered, and an exception is raised. Once the script runs out, polls return no
    messages - which is how a real idle broker behaves, and must not end the stream.
    """

    def __init__(self, *args: _t.Any, script: list[_t.Any], **kwargs: _t.Any) -> None:
        """Instantiates the reader.

        Args:
            *args: Positional arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
            script: The per-poll outcomes to play back.
            **kwargs: Keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        super().__init__(*args, **kwargs)
        self.script = script
        self.polls = 0
        self.connects = 0
        self.disconnects = 0
        self.acked: list[list[_t.Any]] = []

    async def _connect(self) -> None:
        self.connects += 1

    async def _disconnect(self) -> None:
        self.disconnects += 1

    async def _receive(self) -> list[_t.Any]:
        outcome = self.script[self.polls] if self.polls < len(self.script) else []
        self.polls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return _t.cast(list[_t.Any], outcome)

    async def _convert(self, data: list[_t.Any]) -> dict[str, deque]:
        return {field: deque(record.get(field) for record in data) for field in self.io.outputs}

    async def _ack(self, messages: list[_t.Any]) -> None:
        self.acked.append(list(messages))


class UnreconnectableReader(ScriptedReader):
    """A reader whose first connect succeeds and every reconnect afterwards fails."""

    async def _connect(self) -> None:
        self.connects += 1
        if self.connects > 1:
            raise OSError("broker unreachable")


class UndisconnectableReader(ScriptedReader):
    """A reader whose disconnect always fails, as it does when the link is already gone."""

    async def _disconnect(self) -> None:
        self.disconnects += 1
        raise OSError("connection already lost")


MESSAGES = [
    {"x": 1, "y": "a"},
    {"x": 2, "y": "b"},
    {"x": 3, "y": "c"},
    {"x": 4, "y": "d"},
    {"x": 5, "y": "e"},
]


def make_reader(script: list[_t.Any], *, max_retries: int = 3, **kwargs: _t.Any) -> ScriptedReader:
    """Builds a `ScriptedReader` over the `x`/`y` test fields."""
    kwargs.setdefault("field_names", ["x", "y"])
    kwargs.setdefault("topic", "test-topic")
    kwargs.setdefault("idle_poll_delay", 0.0)
    kwargs.setdefault("retry_policy", RetryPolicy(max_retries=max_retries))
    return ScriptedReader(name="test-reader", script=script, **kwargs)


async def drain(reader: ScriptedReader, limit: int = 100) -> list[dict[str, _t.Any]]:
    """Steps a reader until its stream closes, collecting the records it published."""
    records: list[dict[str, _t.Any]] = []
    for _ in range(limit):
        try:
            await reader.step()
        except IOStreamClosedError:
            return records
        records.append({"x": reader.x, "y": reader.y})  # type: ignore[attr-defined]
    raise AssertionError(f"Reader did not finish within {limit} steps")


@pytest.fixture
def backoff_delays(monkeypatch: pytest.MonkeyPatch) -> _t.Iterator[list[float]]:
    """Captures the non-zero backoff delays applied by the retry helper.

    Only the retry module's `asyncio` reference is replaced: patching `asyncio.sleep`
    globally would also break the event loop teardown that waits for pending tasks.
    """
    delays: list[float] = []

    async def _fake_sleep(delay: float, *args: _t.Any) -> None:
        if delay:  # Idle poll pacing is not a backoff delay.
            delays.append(delay)

    monkeypatch.setattr(retry_utils, "asyncio", _t.cast(_t.Any, SimpleNamespace(sleep=_fake_sleep)))
    yield delays


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_init_connects_and_starts_prefetch() -> None:
    """Tests that `init` connects and pre-fetches without waiting for data."""
    reader = make_reader([MESSAGES[:2]])
    await reader.init()
    assert reader.connects == 1
    prefetch = reader._task
    assert prefetch is not None
    # The pre-fetch runs as a task, so `init` never blocks on the broker.
    assert await prefetch == MESSAGES[:2]
    assert reader.polls == 1
    await reader.destroy()


async def test_destroy_disconnects() -> None:
    """Tests that `destroy` stops the pre-fetch and disconnects."""
    reader = make_reader([MESSAGES])
    await reader.init()
    await reader.step()
    await reader.destroy()
    assert reader.disconnects == 1
    assert reader._task is None


async def test_topic_is_retained() -> None:
    """Tests that the topic is kept for broker identification and logging."""
    reader = make_reader([], topic="my-topic")
    assert reader._topic == "my-topic"
    await reader.destroy()


# ---------------------------------------------------------------------------
# Reading records
# ---------------------------------------------------------------------------


async def test_step_publishes_records_in_order() -> None:
    """Tests that records are published one per step, in broker order."""
    reader = make_reader([MESSAGES, NoMoreDataException()])
    await reader.init()
    assert await drain(reader) == MESSAGES
    await reader.destroy()


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5])
async def test_reads_across_batch_boundaries(chunk_size: int) -> None:
    """Tests that splitting messages over several polls loses nothing."""
    batches = [MESSAGES[i : i + chunk_size] for i in range(0, len(MESSAGES), chunk_size)]
    reader = make_reader([*batches, NoMoreDataException()], chunk_size=chunk_size)
    await reader.init()
    assert await drain(reader) == MESSAGES
    await reader.destroy()


async def test_missing_fields_read_as_none() -> None:
    """Tests that a field absent from a message reads as `None`."""
    reader = make_reader([[{"x": 1}], NoMoreDataException()])
    await reader.init()
    await reader.step()
    assert reader.x == 1  # type: ignore[attr-defined]
    assert reader.y is None  # type: ignore[attr-defined]
    await reader.destroy()


async def test_single_field_reader() -> None:
    """Tests a reader with a single output field."""
    reader = ScriptedReader(
        name="test-reader",
        field_names=["value"],
        topic="test-topic",
        idle_poll_delay=0.0,
        script=[[{"value": 0}, {"value": 1}], NoMoreDataException()],
    )
    await reader.init()
    values = []
    for _ in range(2):
        await reader.step()
        values.append(reader.value)  # type: ignore[attr-defined]
    assert values == [0, 1]
    with pytest.raises(IOStreamClosedError):
        await reader.step()
    await reader.destroy()


# ---------------------------------------------------------------------------
# Empty polls are not the end of the stream
# ---------------------------------------------------------------------------


async def test_empty_poll_waits_for_late_messages() -> None:
    """Tests that idle polls do not end the stream, so late messages are still read.

    A reader that starts before its producer must keep running: two empty polls are
    followed by a batch, and `step()` returns that record rather than raising.
    """
    reader = make_reader([[], [], [{"x": 9, "y": "z"}], NoMoreDataException()])
    await reader.init()

    await reader.step()

    assert (reader.x, reader.y) == (9, "z")  # type: ignore[attr-defined]
    assert reader.polls >= 3
    assert not reader.io.is_closed
    await reader.destroy()


async def test_idle_polls_do_not_publish_or_ack() -> None:
    """Tests that empty polls neither emit records nor acknowledge anything."""
    reader = make_reader([[], [], MESSAGES[:1], NoMoreDataException()])
    await reader.init()
    records = await drain(reader)
    assert records == MESSAGES[:1]
    assert reader.polls == 4
    assert len(reader.acked) == 1
    await reader.destroy()


async def test_no_dangling_task_when_source_exhausted() -> None:
    """Tests that exhaustion closes the stream and leaves no task behind."""
    reader = make_reader([NoMoreDataException()])
    await reader.init()
    with pytest.raises(IOStreamClosedError):
        await reader.step()
    assert reader._task is None
    await reader.destroy()


# ---------------------------------------------------------------------------
# Acknowledgment timing
# ---------------------------------------------------------------------------


async def test_batch_acked_only_after_its_last_record_is_consumed() -> None:
    """Tests that a batch is acknowledged once, after every record was published.

    Acknowledging earlier would lose the remaining messages on a crash, so this is the
    at-least-once guarantee for the batch.
    """
    reader = make_reader([MESSAGES[:3], NoMoreDataException()], chunk_size=3)
    await reader.init()

    await reader.step()
    await reader.step()
    assert reader.acked == []  # Two of three records consumed: nothing acked yet.

    await reader.step()  # The third record drains the batch.
    assert [[msg["x"] for msg in batch] for batch in reader.acked] == [[1, 2, 3]]
    await reader.destroy()


async def test_every_consumed_record_is_acknowledged_once() -> None:
    """Tests that the acked messages are exactly the messages that were published."""
    batches = [MESSAGES[:2], MESSAGES[2:]]
    reader = make_reader([*batches, NoMoreDataException()])
    await reader.init()
    await drain(reader)

    acked = [msg["x"] for batch in reader.acked for msg in batch]
    assert acked == [msg["x"] for msg in MESSAGES]
    await reader.destroy()


async def test_unconsumed_messages_are_not_acknowledged() -> None:
    """Tests that destroying mid-batch leaves the unread messages for redelivery."""
    reader = make_reader([MESSAGES])
    await reader.init()
    await reader.step()
    await reader.destroy()
    assert reader.acked == []


# ---------------------------------------------------------------------------
# Retry and reconnection
# ---------------------------------------------------------------------------


async def test_transient_receive_failure_reconnects_and_recovers(
    backoff_delays: list[float],
) -> None:
    """Tests that a transient failure is retried after reconnecting."""
    reader = make_reader(
        [MessageBrokerTransientError("blip"), MESSAGES[:2], NoMoreDataException()],
        max_retries=3,
    )
    await reader.init()
    assert await drain(reader) == MESSAGES[:2]
    assert reader.connects == 2  # Initial connect plus one reconnect.
    assert reader.disconnects == 1
    assert backoff_delays == [1.0]  # Base delay on the first retry.
    await reader.destroy()


async def test_retry_exhaustion_raises_last_broker_error(backoff_delays: list[float]) -> None:
    """Tests that retries are bounded and the broker's own error is raised."""
    failures = [ConnectionError(f"failure {index}") for index in range(5)]
    reader = make_reader(failures, max_retries=2)
    await reader.init()

    with pytest.raises(ConnectionError, match="failure 2"):
        await reader.step()

    assert reader.polls == 3  # Initial attempt plus two retries.
    assert reader.connects == 3  # Initial connect plus one reconnect per retry.
    assert reader.disconnects == 2
    assert backoff_delays == [1.0, 2.0]
    await reader.destroy()


async def test_backoff_delay_is_capped(backoff_delays: list[float]) -> None:
    """Tests that exponential backoff stops growing at `max_delay`."""
    policy = RetryPolicy(max_retries=5, base_delay=1.0, max_delay=3.0)
    reader = make_reader([ConnectionError("down")] * 6, retry_policy=policy)
    await reader.init()

    with pytest.raises(ConnectionError):
        await reader.step()

    assert backoff_delays == [1.0, 2.0, 3.0, 3.0, 3.0]
    await reader.destroy()


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 1.0), (1, 2.0), (2, 4.0), (10, 60.0)],
)
def test_retry_policy_delay_for(attempt: int, expected: float) -> None:
    """Tests that the backoff formula doubles per attempt and respects the cap."""
    assert RetryPolicy().delay_for(attempt) == expected


async def test_permanent_error_is_not_retried() -> None:
    """Tests that a permanent broker error propagates after a single attempt."""
    reader = make_reader(
        [MessageBrokerPermanentError("access denied"), MESSAGES],
        max_retries=3,
    )
    await reader.init()

    with pytest.raises(MessageBrokerPermanentError, match="access denied"):
        await reader.step()

    assert reader.polls == 1
    assert reader.connects == 1  # No reconnect attempted.
    await reader.destroy()


async def test_failing_disconnect_still_reconnects() -> None:
    """Tests that a broken connection is not mistaken for a reason to give up reconnecting.

    The disconnect during a reconnect is expected to fail when the link already dropped,
    so it must not prevent the new connection from being made.
    """
    reader = UndisconnectableReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        idle_poll_delay=0.0,
        script=[ConnectionError("blip"), MESSAGES[:1], NoMoreDataException()],
        retry_policy=RetryPolicy(max_retries=3),
    )
    await reader.init()

    assert await drain(reader) == MESSAGES[:1]
    assert reader.connects == 2  # Initial connect plus one reconnect.
    assert reader.disconnects == 1

    # A disconnect that fails during teardown is surfaced rather than hidden.
    with pytest.raises(OSError, match="connection already lost"):
        await reader.destroy()


async def test_reconnect_failure_does_not_abort_retries(
    backoff_delays: list[float],
) -> None:
    """Tests that a failing reconnect costs an attempt instead of ending the retrying.

    During a network partition the read and the reconnect can both fail; the reader must
    still use up its retries and then report the broker error.
    """
    reader = UnreconnectableReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        idle_poll_delay=0.0,
        script=[ConnectionError("read failed")] * 3,
        retry_policy=RetryPolicy(max_retries=2),
    )
    await reader.init()

    with pytest.raises(ConnectionError, match="read failed"):
        await reader.step()

    assert reader.polls == 3  # All three attempts ran, despite the reconnect failures.
    assert reader.connects == 3  # Initial connect plus one per retry.
    assert backoff_delays == [1.0, 2.0]
    await reader.destroy()
