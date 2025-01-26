"""Unit tests for pubsub mode connector."""

import asyncio
from itertools import cycle
import string

import pytest

from plugboard.connector import (
    Channel,
    Connector,
    ConnectorSpec,
    ZMQConnector,
)
from plugboard.exceptions import ChannelClosedError


TEST_ITEMS = string.ascii_lowercase


async def send_messages(channel: Channel) -> list[str]:
    """Tests helper function to send messages over channels."""
    input_cycle = cycle(TEST_ITEMS)
    sent = [None] * 10
    for i in range(10):
        item = next(input_cycle)
        await channel.send(item)
        sent[i] = item
    return sent


async def recv_messages(channels: list[Channel]) -> list[list[str]]:
    # TODO # For large numbers of test channels and messages, e.g., 1000 * 1000,000 this will require a lot of memory.
    #      # Should return a list of combined hashes of the received message sets instead.
    recvd = [[None] * 10] * len(channels)
    tasks = [None] * len(channels)
    j = 0
    while True:
        async with asyncio.TaskGroup() as tg:
            for i, channel in channels:
                tasks[i] = tg.create_task(channel.recv())
        for i, task in tasks:
            recvd[i][j] = await task.result()
        raise NotImplementedError("Implement stopping condition based on channel closed exception")
    return recvd


@pytest.mark.anyio
@pytest.mark.parametrize("connector_cls", [ZMQConnector])
async def test_channel(connector_cls: type[Connector]) -> None:
    """Tests the various `Channel` classes."""
    connector_spec = ConnectorSpec(
        source="pubsub-test.publishers",
        target="pubsub-test.subscribers",
        mode="pubsub",
    )
    connector = connector_cls(connector_spec)

    publisher = connector.connect_send()
    subscribers = [connector.connect_recv() for _ in range(3)]

    async with asyncio.TaskGroup() as tg:
        sent_msgs = tg.create_task(send_messages(publisher))
        recvd_msgs = tg.create_task(recv_messages(subscribers))

    # TODO : Test assertions.

    with pytest.raises(ChannelClosedError):
        await channel.recv()
    with pytest.raises(ChannelClosedError):
        await channel.send(123)
    assert channel.is_closed
