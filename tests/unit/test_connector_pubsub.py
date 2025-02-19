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
from plugboard.schemas.connector import ConnectorMode, ConnectorSpec


TEST_ITEMS = string.ascii_lowercase
_HASH_SEED = time.time()


@lru_cache(maxsize=int(1e6))
def _get_hash(x: _t.Any) -> int:
    return hash(x)


async def send_messages(channels: list[Channel], num_messages: int) -> int:
    """Test helper function to send messages over publisher channels.

    Returns aggregated hash of all sent messages for the publishers.
    """
    channel_cycle = cycle(channels)
    input_cycle = cycle(TEST_ITEMS)
    _hash = _get_hash(_HASH_SEED)
    for _ in range(num_messages):
        channel = next(channel_cycle)
        item = next(input_cycle)
        await channel.send(item)
        _hash = _get_hash(str(_hash) + str(item))
    for channel in channels:
        await channel.close()
    return _hash


async def recv_messages(channels: list[Channel]) -> list[int]:
    """Test helper function to receive messages over multiple subscriber channels.

    Returns list of aggregated hashes of all received messages for each subscriber.
    """
    hashes = [_get_hash(_HASH_SEED)] * len(channels)
    try:
        while True:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(channel.recv()) for channel in channels]
            for i, task in enumerate(tasks):
                msg = task.result()
                hashes[i] = _get_hash(str(hashes[i]) + str(msg))
    except* ChannelClosedError:
        pass
    return hashes


@pytest.mark.anyio
@pytest.mark.parametrize(
    "connector_cls, num_subscribers, num_messages",
    [
        (ZMQConnector, 1, 1000),
        (ZMQConnector, 100, 1000),
    ],
)
async def test_pubsub_channel_single_publisher(
    connector_cls: type[Connector], num_subscribers: int, num_messages: int
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there is a single publisher. Messages are expected to be received
    by all subscribers exactly once and in order.
    """
    num_publishers: int = 1
    connector_spec = ConnectorSpec(
        source="pubsub-test.publishers",
        target="pubsub-test.subscribers",
        mode=ConnectorMode.PUBSUB,
    )
    connector = connector_cls(connector_spec)

    async with asyncio.TaskGroup() as tg:
        publisher_conn_tasks = [
            tg.create_task(connector.connect_send()) for _ in range(num_publishers)
        ]
        subscriber_conn_tasks = [
            tg.create_task(connector.connect_recv()) for _ in range(num_subscribers)
        ]

    publishers = [t.result() for t in publisher_conn_tasks]
    subscribers = [t.result() for t in subscriber_conn_tasks]

    # Give some time to establish connections
    asyncio.sleep(1)

    async with asyncio.TaskGroup() as tg:
        publisher_send_task = tg.create_task(send_messages(publishers, num_messages))
        subscriber_recv_tasks = tg.create_task(recv_messages(subscribers))

    sent_msgs_hash = publisher_send_task.result()
    received_msgs_hashes = subscriber_recv_tasks.result()

    assert all((x == sent_msgs_hash for x in received_msgs_hashes))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "connector_cls, num_publishers, num_subscribers, num_messages",
    [
        (ZMQConnector, 10, 1, 1000),
        (ZMQConnector, 10, 100, 1000),
    ],
)
async def test_pubsub_channel_multiple_publshers(
    connector_cls: type[Connector], num_publishers: int, num_subscribers: int, num_messages: int
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there is are multiple publishers. Messages are expected to be received
    by all subscribers exactly once but they are not expected to be in order.
    """
    connector_spec = ConnectorSpec(
        source="pubsub-test.publishers",
        target="pubsub-test.subscribers",
        mode=ConnectorMode.PUBSUB,
    )
    connector = connector_cls(connector_spec)

    async with asyncio.TaskGroup() as tg:
        publisher_conn_tasks = [
            tg.create_task(connector.connect_send()) for _ in range(num_publishers)
        ]
        subscriber_conn_tasks = [
            tg.create_task(connector.connect_recv()) for _ in range(num_subscribers)
        ]

    publishers = [t.result() for t in publisher_conn_tasks]
    subscribers = [t.result() for t in subscriber_conn_tasks]

    # Give some time to establish connections
    asyncio.sleep(1)

    async with asyncio.TaskGroup() as tg:
        publisher_send_task = tg.create_task(send_messages(publishers, num_messages))
        subscriber_recv_tasks = tg.create_task(recv_messages(subscribers))

    sent_msgs_hash = publisher_send_task.result()
    received_msgs_hashes = subscriber_recv_tasks.result()

    assert all((x == sent_msgs_hash for x in received_msgs_hashes))
