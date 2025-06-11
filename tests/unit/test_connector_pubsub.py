"""Unit tests for pubsub mode connector."""

import asyncio
from functools import lru_cache
from itertools import cycle
import os
import random
import string
import time
import typing as _t
from unittest.mock import patch

import pytest
import pytest_cases

from plugboard.connector import (
    AsyncioConnector,
    Channel,
    Connector,
    ZMQConnector,
)
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.connector import ConnectorMode, ConnectorSpec
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings


@pytest_cases.fixture
@pytest_cases.parametrize(zmq_pubsub_proxy=[False])
def zmq_connector_cls(zmq_pubsub_proxy: bool) -> _t.Iterator[_t.Type[ZMQConnector]]:
    """Returns the ZMQConnector class with the specified proxy setting.

    Patches the env var `PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY` to control the proxy setting.
    """
    with patch.dict(
        os.environ,
        {"PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY": str(zmq_pubsub_proxy)},
    ):
        testing_settings = Settings()
        DI.settings.override_sync(testing_settings)
        yield ZMQConnector
        DI.settings.reset_override_sync()


@pytest_cases.fixture
@pytest_cases.parametrize(_connector_cls=[AsyncioConnector, zmq_connector_cls])
def connector_cls(_connector_cls: type[Connector]) -> type[Connector]:
    """Fixture for `Connector` of various types."""
    return _connector_cls


TEST_ITEMS = string.ascii_lowercase
_HASH_SEED = time.time()


@lru_cache(maxsize=int(1e6))
def _get_hash(x: _t.Any) -> int:
    return hash(x)


async def send_messages_ordered(channels: list[Channel], num_messages: int) -> int:
    """Test helper function to send messages over publisher channels.

    Returns aggregated hash of all sent messages for the publishers to check for ordered delivery.
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


async def recv_messages_ordered(channels: list[Channel]) -> list[int]:
    """Test helper function to receive messages over multiple subscriber channels.

    Returns list of aggregated hashes of all received messages for each subscriber to check for
    receipt in correct order.
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


async def send_messages_unordered(
    channels: list[Channel], num_messages: int, seed: int | float | None = None
) -> int:
    """Test helper function to send messages over publisher channels.

    Returns sum of all values in sent messages for the publishers to check for delivery of all
    messages exactly once.
    """
    # Setup random number generator with random seed
    rng = random.Random(seed or time.time())  # noqa: S311
    _sum = 0
    channel_cycle = cycle(channels)
    for _ in range(num_messages):
        channel = next(channel_cycle)
        # Generate a random number between -1000 and +1000
        val = rng.randint(-1000, 1000)
        await channel.send(val)
        _sum += val
    # Give some time for messages to be sent before closing channels
    await asyncio.sleep(1)
    for channel in channels:
        await channel.close()
    return _sum


async def recv_messages_unordered(channels: list[Channel]) -> list[int]:
    """Test helper function to receive messages over multiple subscriber channels.

    Returns list of message sums of all received messages for each subscriber to confirm all
    messages received exactly once.
    """
    sums = [0] * len(channels)
    try:
        while True:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(channel.recv()) for channel in channels]
            for i, task in enumerate(tasks):
                msg = task.result()
                sums[i] += msg
    except* ChannelClosedError:
        pass
    return sums


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "connector_cls, num_subscribers, num_messages",
    [
        (connector_cls, 1, 100),
        (connector_cls, 10, 100),
    ],
)
async def test_pubsub_channel_single_publisher(
    connector_cls: type[Connector], num_subscribers: int, num_messages: int, job_id_ctx: str
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there is a single publisher. Messages are expected to be received by all
    subscribers exactly once and in order.
    """
    await _test_pubsub_channel_single_publisher(connector_cls, num_subscribers, num_messages)


async def _test_pubsub_channel_single_publisher(
    connector_cls: type[Connector], num_subscribers: int, num_messages: int
) -> None:
    num_publishers: int = 1
    connector_spec = ConnectorSpec(
        source="pubsub-test-0.publishers",
        target="pubsub-test-0.subscribers",
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
    await asyncio.sleep(1)

    async with asyncio.TaskGroup() as tg:
        publisher_send_task = tg.create_task(send_messages_ordered(publishers, num_messages))
        subscriber_recv_tasks = tg.create_task(recv_messages_ordered(subscribers))

    sent_msgs_hash = publisher_send_task.result()
    received_msgs_hashes = subscriber_recv_tasks.result()

    assert len(set(received_msgs_hashes)) == 1
    assert sent_msgs_hash == received_msgs_hashes[0]


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "connector_cls, num_publishers, num_subscribers, num_messages",
    [
        (connector_cls, 10, 1, 100),
        (connector_cls, 10, 10, 100),
    ],
)
async def test_pubsub_channel_multiple_publishers(
    connector_cls: type[Connector],
    num_publishers: int,
    num_subscribers: int,
    num_messages: int,
    job_id_ctx: str,
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there are multiple publishers. Messages are expected to be received by all
    subscribers exactly once but they are not expected to be in order.
    """
    await _test_pubsub_channel_multiple_publishers(
        connector_cls, num_publishers, num_subscribers, num_messages
    )


async def _test_pubsub_channel_multiple_publishers(
    connector_cls: type[Connector], num_publishers: int, num_subscribers: int, num_messages: int
) -> None:
    connector_spec = ConnectorSpec(
        source="pubsub-test-1.publishers",
        target="pubsub-test-1.subscribers",
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
    await asyncio.sleep(1)

    async with asyncio.TaskGroup() as tg:
        publisher_send_task = tg.create_task(send_messages_unordered(publishers, num_messages))
        subscriber_recv_tasks = tg.create_task(recv_messages_unordered(subscribers))

    sent_msgs_sum = publisher_send_task.result()
    received_msgs_sums = subscriber_recv_tasks.result()

    assert len(set(received_msgs_sums)) == 1
    assert sent_msgs_sum == received_msgs_sums[0]


@pytest.mark.asyncio
@pytest_cases.parametrize(
    "connector_cls, num_topics, num_publishers, num_subscribers, num_messages",
    [
        (connector_cls, 3, 10, 1, 100),
        (connector_cls, 3, 10, 10, 100),
    ],
)
async def test_pubsub_channel_multiple_topics_and_publishers(
    connector_cls: type[Connector],
    num_topics: int,
    num_publishers: int,
    num_subscribers: int,
    num_messages: int,
    job_id_ctx: str,
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there are multiple topics and publishers. Messages are expected to be received by
    all subscribers exactly once but they are not expected to be in order.
    """
    await _test_pubsub_channel_multiple_topics_and_publishers(
        connector_cls, num_topics, num_publishers, num_subscribers, num_messages
    )


async def _test_pubsub_channel_multiple_topics_and_publishers(
    connector_cls: type[Connector],
    num_topics: int,
    num_publishers: int,
    num_subscribers: int,
    num_messages: int,
) -> None:
    all_publishers = []
    all_subscribers = []

    # Create connectors and channels for each topic
    for i in range(num_topics):
        connector_spec = ConnectorSpec(
            source=f"pubsub-test-2-{i}.publishers",
            target=f"pubsub-test-2-{i}.subscribers",
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

        all_publishers.append(publishers)
        all_subscribers.append(subscribers)

    # Give some time to establish connections
    await asyncio.sleep(1)

    publisher_send_tasks = []
    subscriber_recv_tasks = []
    async with asyncio.TaskGroup() as tg:
        for i in range(num_topics):
            publisher_send_tasks.append(
                tg.create_task(send_messages_unordered(all_publishers[i], num_messages))
            )
            subscriber_recv_tasks.append(
                tg.create_task(recv_messages_unordered(all_subscribers[i]))
            )

    sent_msgs_sums = [t.result() for t in publisher_send_tasks]
    all_received_msgs_sums = [t.result() for t in subscriber_recv_tasks]

    # Each subscriber should receive messages from all topics
    assert all(len(set(received_msgs_sums)) == 1 for received_msgs_sums in all_received_msgs_sums)
    assert all(
        sent_msgs_sum == received_msgs_sums[0]
        for sent_msgs_sum, received_msgs_sums in zip(sent_msgs_sums, all_received_msgs_sums)
    )
