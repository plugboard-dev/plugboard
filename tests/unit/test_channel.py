"""Unit tests for channels."""

import asyncio

from multiprocess import Process
import pytest

from plugboard.connector import AsyncioChannel, Channel, ZMQChannel
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.io import IODirection


TEST_ITEMS = [
    45,
    23.456,
    "hello",
    b"world",
    {"a": 1, "b": 2},
    ["this", 15],
    {"a", "test"},
]


@pytest.mark.anyio
@pytest.mark.parametrize("channel_cls", [AsyncioChannel, ZMQChannel])
async def test_channel(channel_cls: type[Channel]) -> None:
    """Tests the various `Channel` classes."""
    channel = channel_cls()
    await asyncio.gather(channel.connect(IODirection.INPUT), channel.connect(IODirection.OUTPUT))

    for item in TEST_ITEMS:
        await channel.send(item)

    await channel.close()

    for item in TEST_ITEMS:
        assert await channel.recv() == item

    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.send(123)
    assert channel.is_closed


@pytest.mark.parametrize("channel_cls", [ZMQChannel])
def test_multiprocessing_channel(channel_cls: type[Channel]) -> None:
    """Tests the various `Channel` classes in a multiprocess environment."""
    channel = channel_cls()

    async def _send_proc_async(channel: Channel) -> None:
        await channel.connect(IODirection.OUTPUT)
        for item in TEST_ITEMS:
            await channel.send(item)
        await channel.close()
        assert channel.is_closed

    async def _recv_proc_async(channel: Channel) -> None:
        await channel.connect(IODirection.INPUT)
        for item in TEST_ITEMS:
            assert await channel.recv() == item
        with pytest.raises(ChannelClosedError):
            await channel.recv()

    def _send_proc(channel: Channel) -> None:
        asyncio.run(_send_proc_async(channel))

    def _recv_proc(channel: Channel) -> None:
        asyncio.run(_recv_proc_async(channel))

    send_proc = Process(target=_send_proc, args=(channel,))
    recv_proc = Process(target=_recv_proc, args=(channel,))
    send_proc.start()
    recv_proc.start()
    send_proc.join()
    recv_proc.join()
    assert send_proc.exitcode == recv_proc.exitcode == 0
