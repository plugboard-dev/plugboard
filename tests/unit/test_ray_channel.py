"""Regression tests for Ray channel and connector initialization."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from plugboard.connector import RayChannel, RayConnector
from plugboard.schemas import ConnectorSpec


@pytest.mark.asyncio
async def test_direct_channel_operations_need_no_initialization() -> None:
    """A directly constructed channel can send, receive, and close immediately."""
    with patch("plugboard.connector.ray_channel.ray.remote") as remote:
        actor_class = remote.return_value.return_value
        actor = actor_class.remote.return_value
        actor.send.remote = AsyncMock()
        actor.recv.remote = AsyncMock(return_value="message")
        actor.close.remote = AsyncMock()

        channel = RayChannel(actor_options={"num_cpus": 1}, maxsize=3)
        await channel.send("message")
        assert await channel.recv() == "message"
        await channel.close()

        remote.assert_called_once_with(num_cpus=1)
        actor_class.remote.assert_called_once_with(maxsize=3)
        actor.send.remote.assert_awaited_once_with("message")
        actor.recv.remote.assert_awaited_once_with()
        actor.close.remote.assert_awaited_once_with()


@pytest.mark.parametrize("property_name", ["maxsize", "is_closed"])
def test_direct_channel_properties_need_no_initialization(property_name: str) -> None:
    """Property access preserves the remote reference returned by the actor."""
    with patch("plugboard.connector.ray_channel.ray.remote") as remote:
        actor = remote.return_value.return_value.remote.return_value
        channel = RayChannel()

        assert getattr(channel, property_name) is actor.getattr.remote.return_value

        remote.assert_called_once_with(num_cpus=0)
        actor.getattr.remote.assert_called_once_with(property_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("initialize_first", [False, True])
async def test_connector_defers_and_shares_channel(initialize_first: bool) -> None:
    """Explicit init and concurrent connections create one shared actor on demand."""
    with patch("plugboard.connector.ray_channel.ray.remote") as remote:
        connector = RayConnector(spec=ConnectorSpec(source="source.value", target="sink.value"))
        remote.assert_not_called()

        if initialize_first:
            await connector.init()

        sender, receiver = await asyncio.gather(connector.connect_send(), connector.connect_recv())
        await connector.init()

        assert isinstance(sender, RayChannel)
        assert sender is receiver
        assert await connector.connect_send() is sender
        assert await connector.connect_recv() is receiver
        remote.assert_called_once_with(num_cpus=0)
        remote.return_value.return_value.remote.assert_called_once_with()
