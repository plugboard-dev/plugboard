"""Unit tests for the `ChannelBuilder` and `ChannelBuilderRegistry` classes."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest

from plugboard.connector.channel import Channel
from plugboard.connector.connector import Connector
from plugboard.connector.connector_builder import ConnectorBuilder
from plugboard.schemas.connector import ConnectorMode, ConnectorSpec


class MyChannel(Channel):
    def __init__(self, a: int, **kwargs: dict[str, _t.Any]) -> None:
        self._a = a
        self._kwargs = kwargs

    async def send(self, msg: int) -> None:
        return

    async def recv(self) -> int:
        return 0


class MyConnector(Connector):
    def __init__(
        self,
        spec: ConnectorSpec,
        *args: _t.Any,
        a: int = 0,
        b: _t.Optional[int] = None,
        **kwds: _t.Any,
    ) -> None:
        self.spec = spec
        self._a = a
        self._b = b

    async def connect_recv(self) -> MyChannel:
        kwargs: dict[str, _t.Any] = {"b": self._b} if self._b is not None else {}
        return MyChannel(a=self._a, **kwargs)

    async def connect_send(self) -> MyChannel:
        kwargs: dict[str, _t.Any] = {"b": self._b} if self._b is not None else {}
        return MyChannel(a=self._a, **kwargs)


@pytest.mark.asyncio
async def test_connector_builder() -> None:
    """Tests the `ConnectorBuilder`."""
    cs = ConnectorSpec(mode=ConnectorMode.PIPELINE, source="test1.a", target="test2.b")

    connector_builder = ConnectorBuilder(connector_cls=MyConnector, a=1)
    connector1 = connector_builder.build(cs)
    # Check that the connector was built correctly
    assert isinstance(connector1, MyConnector)
    assert connector1.spec == cs
    assert connector1._a == 1
    assert connector1._b is None

    # Check that the channel was built correctly
    channel1 = await connector1.connect_recv()
    assert isinstance(channel1, MyChannel)
    assert channel1._a == 1
    assert channel1._kwargs == {}

    connector_builder = ConnectorBuilder(connector_cls=MyConnector, a=1, b=2)
    connector2 = connector_builder.build(cs)
    # Check that the connector was built correctly
    assert isinstance(connector2, MyConnector)
    assert connector2.spec == cs
    assert connector2._a == 1
    assert connector2._b == 2

    channel2 = await connector2.connect_send()
    # Check that the channel was built correctly
    assert isinstance(channel2, MyChannel)
    assert channel2._a == 1
    assert channel2._kwargs == {"b": 2}
