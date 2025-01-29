"""Unit tests for pubsub mode connector."""

import asyncio
from functools import lru_cache
from itertools import cycle
import string
import time
import typing as _t

import pytest

from plugboard.connector import (
    Channel,
    Connector,
    ZMQConnector,
)
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.connector import ConnectorSpec


TEST_ITEMS = string.ascii_lowercase
_HASH_SEED = time.time()


@lru_cache(maxsize=int(1e6))
def _get_hash(x: _t.Any) -> int:
    return hash(x)


async def send_messages(channel: Channel) -> int:
    """Tests helper function to send messages over publisher channel.

    Returns aggregated hash of all sent messages for the publisher.
    """
    input_cycle = cycle(TEST_ITEMS)
    _hash = _get_hash(_HASH_SEED)
    for _ in range(10):
        item = next(input_cycle)
        await channel.send(item)
        _hash = _get_hash(str(_hash) + str(item))
    await channel.close()
    return _hash


async def recv_messages(channels: list[Channel]) -> list[int]:
    """Test helper function to receive messages over multiple subscriber channels.

    Returns list of aggregated hashes of all received messages for each subscriber.
    """
    _hashes = [_get_hash(_HASH_SEED)] * len(channels)
    tasks: list[asyncio.Task[str]] = [None] * len(channels)  # type: ignore
    try:
        while True:
            async with asyncio.TaskGroup() as tg:
                for i, channel in enumerate(channels):
                    tasks[i] = tg.create_task(channel.recv())
            for i, task in enumerate(tasks):
                msg = task.result()
                _hashes[i] = _get_hash(str(_hashes[i]) + str(msg))
    except ChannelClosedError:
        return _hashes


@pytest.mark.anyio
@pytest.mark.parametrize("connector_cls", [ZMQConnector])
async def test_pubsub_channel(connector_cls: type[Connector]) -> None:
    """Tests the various `Channel` classes."""
    connector_spec = ConnectorSpec(
        source="pubsub-test.publishers",
        target="pubsub-test.subscribers",
        mode="pubsub",
    )
    connector = connector_cls(connector_spec)

    publisher = await connector.connect_send()
    subscribers = await asyncio.gather(*[connector.connect_recv() for _ in range(3)])

    async with asyncio.TaskGroup() as tg:
        publisher_task = tg.create_task(send_messages(publisher))
        subscribers_task = tg.create_task(recv_messages(subscribers))

    sent_msgs_hash = publisher_task.result()
    received_msgs_hashes = subscribers_task.result()

    assert all((x == sent_msgs_hash for x in received_msgs_hashes))
