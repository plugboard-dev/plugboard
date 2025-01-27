"""Unit tests for the `ChannelBuilder` and `ChannelBuilderRegistry` classes."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest

from plugboard.connector.channel import Channel
from plugboard.connector.connector import Connector
from plugboard.connector.connector_builder import ConnectorBuilder


class MyChannel(Channel):
    def __init__(self, a: int, **kwargs: dict[str, _t.Any]) -> None:
        self.a = a
        self.kwargs = kwargs

    async def send(self, msg: int) -> None:
        return

    async def recv(self) -> int:
        return 0


class MyConnector(Connector):
    channel_cls = MyChannel


@pytest.mark.anyio
async def test_connector_builder() -> None:
    """Tests the `ConnectorBuilder`."""
    connector_builder = ConnectorBuilder(connector_cls=MyConnector)
    # TODO : Fix tests!
    channel1 = connector_builder.build(a=1)
    # Check that the channel was built correctly
    assert isinstance(channel1, MyChannel)
    assert channel1.a == 1
    assert channel1.kwargs == {}
    channel2 = connector_builder.build(a=2, b=3)
    # Check that the channel was built correctly
    assert isinstance(channel2, MyChannel)
    assert channel2.a == 2
    assert channel2.kwargs == {"b": 3}
