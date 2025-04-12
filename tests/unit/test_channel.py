"""Unit tests for channels."""

import asyncio

import pytest
import pytest_cases
from ray.util.multiprocessing import Pool

from plugboard.connector import (
    AsyncioConnector,
    Connector,
    ConnectorBuilder,
    RayConnector,
)
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.connector import ConnectorMode, ConnectorSpec
from tests.conftest import zmq_connector_cls


TEST_ITEMS = [
    45,
    23.456,
    "hello",
    b"world",
    {"a": 1, "b": 2},
    ["this", 15],
    {"a", "test"},
]


@pytest.mark.asyncio
@pytest_cases.parametrize("connector_cls", [AsyncioConnector, RayConnector, zmq_connector_cls])
async def test_channel(connector_cls: type[Connector]) -> None:
    """Tests the various Channel implementations."""
    spec = ConnectorSpec(mode=ConnectorMode.PIPELINE, source="test.send", target="test.recv")
    connector = ConnectorBuilder(connector_cls=connector_cls).build(spec)

    send_channel, recv_channel = await asyncio.gather(
        connector.connect_send(), connector.connect_recv()
    )

    # Send/receive first item to initialise the channel
    initial_send_recv = await asyncio.gather(send_channel.send(TEST_ITEMS[0]), recv_channel.recv())
    # Send remaining items in loop to preserve order in distributed case
    for item in TEST_ITEMS[1:]:
        await send_channel.send(item)

    results = [initial_send_recv[1]]
    for _ in TEST_ITEMS[1:]:
        results.append(await recv_channel.recv())
    await send_channel.close()
    await recv_channel.close()

    # Ensure that the sent and received items are the same.
    assert results == TEST_ITEMS, "Failed on iteration: {}".format(iter)

    with pytest.raises(ChannelClosedError):
        await recv_channel.recv()
    with pytest.raises(ChannelClosedError):
        await send_channel.send(123)
    assert recv_channel.is_closed
    assert send_channel.is_closed


@pytest.mark.asyncio
@pytest_cases.parametrize("connector_cls", [zmq_connector_cls])
async def test_multiprocessing_channel(connector_cls: type[Connector]) -> None:
    """Tests the various Channel implementations in a multiprocess environment."""
    spec = ConnectorSpec(mode=ConnectorMode.PIPELINE, source="test.send", target="test.recv")
    connector = ConnectorBuilder(connector_cls=connector_cls).build(spec)

    async def _send_proc_async(connector: Connector) -> None:
        channel = await connector.connect_send()
        await asyncio.sleep(0.1)  # Ensure the receiver is ready before sending messages
        for item in TEST_ITEMS:
            await channel.send(item)
        await channel.close()
        assert channel.is_closed

    async def _recv_proc_async(connector: Connector) -> None:
        channel = await connector.connect_recv()
        for item in TEST_ITEMS:
            assert await channel.recv() == item
        with pytest.raises(ChannelClosedError):
            await channel.recv()

    def _send_proc(connector: Connector) -> None:
        asyncio.run(_send_proc_async(connector))

    def _recv_proc(connector: Connector) -> None:
        asyncio.run(_recv_proc_async(connector))

    # Use a wrapper function to ensure the connector stays in scope
    def run_pool_with_connector(connector: Connector) -> None:
        with Pool(2) as pool:
            r1 = pool.apply_async(_send_proc, (connector,))
            r2 = pool.apply_async(_recv_proc, (connector,))
            r1.get()
            r2.get()

    # Run the pool function while keeping the connector in scope
    await asyncio.to_thread(run_pool_with_connector, connector)
