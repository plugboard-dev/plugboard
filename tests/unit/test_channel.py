"""Unit tests for channels."""

import asyncio

from mpire import WorkerPool
import pytest

from plugboard.connector import AsyncioChannelBuilder, Channel, ChannelBuilder, ZMQChannelBuilder
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


@pytest.mark.anyio
@pytest.mark.parametrize("channel_builder_cls", [AsyncioChannelBuilder, ZMQChannelBuilder])
async def test_channel(channel_builder_cls: type[ChannelBuilder]) -> None:
    """Tests the various `Channel` classes."""
    channel = channel_builder_cls().build()
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


@pytest.mark.parametrize("channel_builder_cls", [ZMQChannelBuilder])
def test_multiprocessing_channel(channel_builder_cls: type[ChannelBuilder]) -> None:
    """Tests the various `Channel` classes in a multiprocess environment."""
    channel = channel_builder_cls().build()

    with WorkerPool(n_jobs=2, use_dill=True) as pool:
        r1 = pool.apply_async(_send_proc, (channel,))
        r2 = pool.apply_async(_recv_proc, (channel,))
        r1.get()
        r2.get()
