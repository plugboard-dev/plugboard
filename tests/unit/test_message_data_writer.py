"""Unit tests for the `MessageDataWriter` base class."""

from __future__ import annotations

from collections import deque
import typing as _t

import pytest

from plugboard.connector import AsyncioConnector
from plugboard.library.message_writer import MessageDataWriter
from plugboard.schemas import ConnectorSpec


# ---------------------------------------------------------------------------
# Mock implementation
# ---------------------------------------------------------------------------


class MockMessageDataWriter(MessageDataWriter):
    """Mock `MessageDataWriter` for testing the base class logic."""

    def __init__(
        self,
        *args: _t.Any,
        fail_on_connect: bool = False,
        fail_on_send: int | None = None,
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._connected = False
        self._disconnected = False
        self._sent_messages: list[list[_t.Any]] = []
        self._fail_on_connect = fail_on_connect
        self._fail_on_send = fail_on_send
        self._send_call_count = 0
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

    async def _send(self, messages: list[_t.Any]) -> None:
        self._send_call_count += 1
        if self._fail_on_send is not None and self._send_call_count == self._fail_on_send:
            raise ConnectionError("Simulated send failure")
        self._sent_messages.append(messages)

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        completed_rows = min(len(d) for d in data.values()) if data else 0
        messages: list[dict[str, _t.Any]] = []
        for i in range(completed_rows):
            record = {field: data[field][i] for field in data}
            messages.append(record)
        return messages


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _setup_writer_with_channels(
    writer: MockMessageDataWriter, field_names: list[str]
) -> dict[str, AsyncioConnector]:
    """Sets up a writer with connected asyncio channels for sending data."""
    connectors = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"{writer.name}.{field}"),
        )
        for field in field_names
    }
    await writer.io.connect(list(connectors.values()))
    return connectors


# ---------------------------------------------------------------------------
# Tests: Basic lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_init() -> None:
    """Tests that `init` connects to the broker."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x", "y"],
        topic="test-topic",
    )
    await writer.init()
    assert writer._connected is True
    assert writer._connect_call_count == 1
    await writer.destroy()


@pytest.mark.asyncio
async def test_message_data_writer_destroy() -> None:
    """Tests that `destroy` disconnects from the broker."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x", "y"],
        topic="test-topic",
    )
    await writer.init()
    await writer.destroy()
    assert writer._disconnected is True
    assert writer._disconnect_call_count == 1


# ---------------------------------------------------------------------------
# Tests: Writing data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_step_and_run() -> None:
    """Tests that data is written via step and flushed on run."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x", "y"],
        topic="test-topic",
        chunk_size=2,
    )
    connectors = await _setup_writer_with_channels(writer, ["x", "y"])
    await writer.init()

    output_channels = {field: await connectors[field].connect_send() for field in ["x", "y"]}

    # Send data
    test_data = [(1, "a"), (2, "b"), (3, "c")]
    for x_val, y_val in test_data:
        await output_channels["x"].send(x_val)
        await output_channels["y"].send(y_val)
        await writer.step()

    # Close inputs and run to flush
    await writer.io.close()
    await writer.run()

    # Verify sent messages
    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert len(all_sent) == 3
    assert all_sent[0] == {"x": 1, "y": "a"}
    assert all_sent[1] == {"x": 2, "y": "b"}
    assert all_sent[2] == {"x": 3, "y": "c"}

    await writer.destroy()


@pytest.mark.asyncio
async def test_message_data_writer_flush_on_run() -> None:
    """Tests that remaining buffered data is flushed on `run`."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x"],
        topic="test-topic",
        chunk_size=10,  # Large chunk size so nothing is sent during step
    )
    connectors = await _setup_writer_with_channels(writer, ["x"])
    await writer.init()

    output_channels = {"x": await connectors["x"].connect_send()}

    # Send data (less than chunk_size)
    for i in range(3):
        await output_channels["x"].send(i)
        await writer.step()

    # Nothing should be sent yet (buffer < chunk_size)
    assert len(writer._sent_messages) == 0

    # Close and run to flush
    await writer.io.close()
    await writer.run()

    # Now data should be flushed
    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert len(all_sent) == 3
    assert all_sent == [{"x": 0}, {"x": 1}, {"x": 2}]

    await writer.destroy()


# ---------------------------------------------------------------------------
# Tests: Chunked writing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5])
async def test_message_data_writer_chunked(chunk_size: int) -> None:
    """Tests writing with various chunk sizes."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x", "y"],
        topic="test-topic",
        chunk_size=chunk_size,
    )
    connectors = await _setup_writer_with_channels(writer, ["x", "y"])
    await writer.init()

    output_channels = {field: await connectors[field].connect_send() for field in ["x", "y"]}

    test_data = [(i, f"val_{i}") for i in range(5)]
    for x_val, y_val in test_data:
        await output_channels["x"].send(x_val)
        await output_channels["y"].send(y_val)
        await writer.step()

    await writer.io.close()
    await writer.run()

    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert len(all_sent) == 5
    for i, (x_val, y_val) in enumerate(test_data):
        assert all_sent[i] == {"x": x_val, "y": y_val}

    await writer.destroy()


@pytest.mark.asyncio
async def test_message_data_writer_no_chunk_size() -> None:
    """Tests writing without chunk size (flush only on run)."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x"],
        topic="test-topic",
        chunk_size=None,
    )
    connectors = await _setup_writer_with_channels(writer, ["x"])
    await writer.init()

    output_channels = {"x": await connectors["x"].connect_send()}

    for i in range(3):
        await output_channels["x"].send(i)
        await writer.step()

    # Nothing sent yet (no chunk_size trigger)
    assert len(writer._sent_messages) == 0

    await writer.io.close()
    await writer.run()

    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert len(all_sent) == 3

    await writer.destroy()


# ---------------------------------------------------------------------------
# Tests: Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_retry_on_send_failure() -> None:
    """Tests that writer retries on transient send failures."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x"],
        topic="test-topic",
        chunk_size=1,
        fail_on_send=1,  # Fail on first send
        max_retries=3,
        retry_base_delay=0.01,
    )
    connectors = await _setup_writer_with_channels(writer, ["x"])
    await writer.init()

    output_channels = {"x": await connectors["x"].connect_send()}

    # Send one item and step (triggers send which fails, then retries)
    await output_channels["x"].send(0)
    await writer.step()

    # Send another item and step (should succeed now)
    await output_channels["x"].send(1)
    await writer.step()

    await writer.io.close()
    await writer.run()

    # Should have retried and eventually succeeded
    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert len(all_sent) == 2
    # Should have reconnected
    assert writer._connect_call_count >= 2

    await writer.destroy()


# ---------------------------------------------------------------------------
# Tests: Connection failure on init
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_connection_failure_on_init() -> None:
    """Tests that init raises on connection failure."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x"],
        topic="test-topic",
        fail_on_connect=True,
    )
    with pytest.raises(ConnectionError):
        await writer.init()


# ---------------------------------------------------------------------------
# Tests: Topic attribute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_topic() -> None:
    """Tests that the topic is stored correctly."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["x"],
        topic="my-topic",
    )
    assert writer._topic == "my-topic"


# ---------------------------------------------------------------------------
# Tests: Single field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_data_writer_single_field() -> None:
    """Tests writing with a single input field."""
    writer = MockMessageDataWriter(
        name="test-writer",
        field_names=["value"],
        topic="test-topic",
        chunk_size=3,
    )
    connectors = await _setup_writer_with_channels(writer, ["value"])
    await writer.init()

    output_channels = {"value": await connectors["value"].connect_send()}

    for i in range(3):
        await output_channels["value"].send(i * 10)
        await writer.step()

    await writer.io.close()
    await writer.run()

    all_sent = [msg for batch in writer._sent_messages for msg in batch]
    assert all_sent == [{"value": 0}, {"value": 10}, {"value": 20}]

    await writer.destroy()
