"""Unit tests for channels."""

import asyncio

import pytest
from ray.util.multiprocessing import Pool

from plugboard.connector import (
    AsyncioChannelBuilder,
    Channel,
    ChannelBuilder,
    RayChannelBuilder,
    ZMQChannelBuilder,
)
from plugboard.exceptions import ChannelClosedError


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
@pytest.mark.parametrize(
    "channel_builder_cls", [AsyncioChannelBuilder, RayChannelBuilder, ZMQChannelBuilder]
)
async def test_channel(channel_builder_cls: type[ChannelBuilder]) -> None:
    """Tests the various `Channel` classes."""
    channel = channel_builder_cls().build()

    # Send/receive first item to initialise the channel
    initial_send_recv = await asyncio.gather(channel.send(TEST_ITEMS[0]), channel.recv())
    # Send remaining items in loop to preserve order in distributed case
    for item in TEST_ITEMS[1:]:
        await channel.send(item)
    recv_coros = [channel.recv() for _ in TEST_ITEMS[1:]]

    results = [initial_send_recv[1]] + await asyncio.gather(*recv_coros)
    await channel.close()

    # Ensure that the sent and received items are the same.
    assert results == TEST_ITEMS

    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.send(123)
    assert channel.is_closed


@pytest.mark.parametrize("channel_builder_cls", [ZMQChannelBuilder])
def test_multiprocessing_channel(channel_builder_cls: type[ChannelBuilder]) -> None:
    """Tests the various `Channel` classes in a multiprocess environment."""
    channel = channel_builder_cls().build()

    async def _send_proc_async(channel: Channel) -> None:
        for item in TEST_ITEMS:
            await channel.send(item)
        await channel.close()
        assert channel.is_closed

    async def _recv_proc_async(channel: Channel) -> None:
        for item in TEST_ITEMS:
            assert await channel.recv() == item
        with pytest.raises(ChannelClosedError):
            await channel.recv()

    def _send_proc(channel: Channel) -> None:
        asyncio.run(_send_proc_async(channel))

    def _recv_proc(channel: Channel) -> None:
        asyncio.run(_recv_proc_async(channel))

    with Pool(2) as pool:
        r1 = pool.apply_async(_send_proc, (channel,))
        r2 = pool.apply_async(_recv_proc, (channel,))
        r1.get()
        r2.get()
