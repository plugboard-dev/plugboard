"""Unit tests for the `MessageDataReader` base class."""

from __future__ import annotations

from collections import deque
import typing as _t

import pytest

from plugboard.exceptions import IOStreamClosedError, NoMoreDataException
from plugboard.library.message_reader import MessageDataReader


# ---------------------------------------------------------------------------
# Mock implementation
# ---------------------------------------------------------------------------


class MockMessageDataReader(MessageDataReader):
    """Mock `MessageDataReader` for testing the base class logic."""

    def __init__(
        self,
        *args: _t.Any,
        messages: list[dict[str, _t.Any]],
        fail_on_connect: bool = False,
        fail_on_receive: int | None = None,
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._messages = messages
        self._idx = 0
        self._connected = False
        self._disconnected = False
        self._acknowledged: list[list[dict[str, _t.Any]]] = []
        self._fail_on_connect = fail_on_connect
        self._fail_on_receive = fail_on_receive
        self._receive_call_count = 0
        self._connect_call_count = 0
        self._disconnect_call_count = 0

    async def _connect(self) -> None:
        self._connect_call_count += 1
        if self._fail_on_connect and self._connect_call_count <= 1:
            raise ConnectionError("Simulated connection failure")
        self._connected = True

    async def _disconnect(self) -> None:
        self._disconnect_call_count += 1
        self._connected = False
        self._disconnected = True

    async def _receive(self) -> list[_t.Any]:
        self._receive_call_count += 1
        if self._fail_on_receive is not None and self._receive_call_count == self._fail_on_receive:
            raise ConnectionError("Simulated receive failure")
        if self._chunk_size:
            chunk = self._messages[self._idx : self._idx + self._chunk_size]
        else:
            chunk = self._messages[self._idx :]
        self._idx += len(chunk)
        if not chunk and self._idx >= len(self._messages):
            raise NoMoreDataException
        return chunk

    async def _convert(self, messages: list[_t.Any]) -> dict[str, deque]:
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for msg in messages:
            for field in self.io.outputs:
                converted[field].append(msg.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        self._acknowledged.append(messages)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

TEST_MESSAGES = [
    {"x": 1, "y": "a"},
    {"x": 2, "y": "b"},
    {"x": 3, "y": "c"},
    {"x": 4, "y": "d"},
    {"x": 5, "y": "e"},
]


# ---------------------------------------------------------------------------
# Tests: Basic lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_init() -> None:
    """Tests that `init` connects to the broker and pre-fetches data."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES,
    )
    await reader.init()
    assert reader._connected is True
    assert reader._connect_call_count == 1
    # First batch should be pre-fetched
    assert reader._receive_call_count == 1
    await reader.destroy()


@pytest.mark.asyncio
async def test_message_data_reader_destroy() -> None:
    """Tests that `destroy` disconnects from the broker."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES,
    )
    await reader.init()
    await reader.destroy()
    assert reader._disconnected is True
    assert reader._disconnect_call_count == 1


@pytest.mark.asyncio
async def test_message_data_reader_step() -> None:
    """Tests that `step` reads one record at a time."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES,
    )
    await reader.init()

    results: list[dict[str, _t.Any]] = []
    while True:
        try:
            await reader.step()
            results.append({"x": reader.x, "y": reader.y})  # type: ignore[attr-defined]
        except IOStreamClosedError:
            break

    assert results == TEST_MESSAGES
    await reader.destroy()


@pytest.mark.asyncio
async def test_message_data_reader_acknowledgment() -> None:
    """Tests that messages are acknowledged after processing."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES,
    )
    await reader.init()

    # Step through first message
    await reader.step()
    # First batch should be acknowledged
    assert len(reader._acknowledged) >= 1

    await reader.destroy()


# ---------------------------------------------------------------------------
# Tests: Chunked reading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 10])
async def test_message_data_reader_chunked(chunk_size: int) -> None:
    """Tests reading with various chunk sizes."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        chunk_size=chunk_size,
        messages=TEST_MESSAGES,
    )
    await reader.init()

    results: list[dict[str, _t.Any]] = []
    while True:
        try:
            await reader.step()
            results.append({"x": reader.x, "y": reader.y})  # type: ignore[attr-defined]
        except IOStreamClosedError:
            break

    assert results == TEST_MESSAGES
    await reader.destroy()


@pytest.mark.asyncio
async def test_message_data_reader_no_chunk_size() -> None:
    """Tests reading without chunk size (all messages at once)."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        chunk_size=None,
        messages=TEST_MESSAGES,
    )
    await reader.init()

    results: list[dict[str, _t.Any]] = []
    while True:
        try:
            await reader.step()
            results.append({"x": reader.x, "y": reader.y})  # type: ignore[attr-defined]
        except IOStreamClosedError:
            break

    assert results == TEST_MESSAGES
    await reader.destroy()


# ---------------------------------------------------------------------------
# Tests: Empty messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_empty_messages() -> None:
    """Tests that reader handles empty message source correctly."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=[],
    )
    await reader.init()

    with pytest.raises(IOStreamClosedError):
        await reader.step()

    await reader.destroy()


# ---------------------------------------------------------------------------
# Tests: Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_retry_on_receive_failure() -> None:
    """Tests that reader retries on transient receive failures."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES[:2],
        fail_on_receive=2,  # Fail on the second receive call
        max_retries=3,
        retry_base_delay=0.01,  # Fast retries for testing
    )
    await reader.init()

    results: list[dict[str, _t.Any]] = []
    while True:
        try:
            await reader.step()
            results.append({"x": reader.x, "y": reader.y})  # type: ignore[attr-defined]
        except IOStreamClosedError:
            break

    assert results == TEST_MESSAGES[:2]
    # Should have attempted reconnection
    assert reader._connect_call_count >= 2
    await reader.destroy()


@pytest.mark.asyncio
async def test_message_data_reader_retry_exhausted() -> None:
    """Tests that reader raises after all retries are exhausted."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES[:1],
        fail_on_receive=2,  # Always fail on receive
        max_retries=2,
        retry_base_delay=0.01,
    )
    await reader.init()

    # First step should succeed (from pre-fetched data)
    await reader.step()

    # Second step should fail after retries exhausted
    with pytest.raises((IOStreamClosedError, ConnectionError)):
        await reader.step()

    await reader.destroy()


# ---------------------------------------------------------------------------
# Tests: Connection failure on init
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_connection_failure_on_init() -> None:
    """Tests that init raises on connection failure."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x", "y"],
        topic="test-topic",
        messages=TEST_MESSAGES,
        fail_on_connect=True,
    )
    with pytest.raises(ConnectionError):
        await reader.init()


# ---------------------------------------------------------------------------
# Tests: Single field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_single_field() -> None:
    """Tests reading with a single output field."""
    messages = [{"value": i} for i in range(3)]
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["value"],
        topic="test-topic",
        messages=messages,
    )
    await reader.init()

    results: list[_t.Any] = []
    while True:
        try:
            await reader.step()
            results.append(reader.value)  # type: ignore[attr-defined]
        except IOStreamClosedError:
            break

    assert results == [0, 1, 2]
    await reader.destroy()


# ---------------------------------------------------------------------------
# Tests: Topic attribute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_reader_topic() -> None:
    """Tests that the topic is stored correctly."""
    reader = MockMessageDataReader(
        name="test-reader",
        field_names=["x"],
        topic="my-topic",
        messages=[{"x": 1}],
    )
    assert reader._topic == "my-topic"
    await reader.init()
    await reader.destroy()
