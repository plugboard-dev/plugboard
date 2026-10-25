"""Regression tests for NumPy payloads in channel receive wrappers."""

import asyncio
import typing as _t

import numpy as np
import numpy.typing as npt
import pytest

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import CHAN_CLOSE_MSG, Channel
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelClosedError


class _InMemorySerdeChannel(SerdeChannel):
    """Exercise the serialized channel wrapper without an external broker."""

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def send(self, msg: bytes) -> None:
        """Queue a serialized message."""
        await self._queue.put(msg)

    async def recv(self) -> bytes:
        """Return a queued serialized message."""
        return await self._queue.get()


@pytest.mark.parametrize("channel_cls", [AsyncioChannel, _InMemorySerdeChannel])
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(np.arange(3), id="vector"),
        pytest.param(np.arange(6).reshape(2, 3), id="matrix"),
        pytest.param(np.array([]), id="empty"),
        pytest.param(np.array(42), id="scalar"),
        pytest.param(np.array([42]), id="singleton"),
        pytest.param(np.array(["a", "b"]), id="strings"),
        pytest.param(np.array([1, "a"], dtype=object), id="objects"),
        pytest.param(np.array([(1, 2.0)], dtype=[("x", "i4"), ("y", "f8")]), id="structured"),
        pytest.param(np.arange(8)[::2], id="noncontiguous"),
        pytest.param(np.array(CHAN_CLOSE_MSG), id="close-marker-scalar"),
        pytest.param(np.array([CHAN_CLOSE_MSG]), id="close-marker-singleton"),
    ],
)
async def test_numpy_payload_round_trip(
    channel_cls: type[Channel], payload: npt.NDArray[_t.Any]
) -> None:
    """Arrays remain data, and the actual close marker still closes the channel."""
    channel = channel_cls()
    await channel.send(payload)
    received = await channel.recv()

    assert isinstance(received, np.ndarray)
    np.testing.assert_array_equal(received, payload)
    assert received.dtype == payload.dtype
    assert received.shape == payload.shape
    assert not channel.is_closed

    await channel.send("next message")
    assert await channel.recv() == "next message"

    await channel.close()
    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.send(payload)
