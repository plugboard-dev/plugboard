"""Unit tests for channels."""

import asyncio

import pytest

from plugboard.connector import AsyncioChannel, Channel, ZMQChannel
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.io import IODirection


@pytest.mark.anyio
@pytest.mark.parametrize("channel_cls", [AsyncioChannel, ZMQChannel])
async def test_zmq_channel(channel_cls: type[Channel]) -> None:
    """Tests the varioud `Channel` classes."""
    channel = channel_cls()
    await asyncio.gather(channel.connect(IODirection.INPUT), channel.connect(IODirection.OUTPUT))
    items = [
        45,
        23.456,
        "hello",
        b"world",
        {"a": 1, "b": 2},
        ["this", 15],
        {"a", "test"},
    ]
    for item in items:
        await channel.send(item)

    await channel.close()

    for item in items:
        assert await channel.recv() == item

    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.send(123)
    assert channel.is_closed
