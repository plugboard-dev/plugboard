"""Unit tests for the `ChannelBuilder` and `ChannelBuilderRegistry` classes."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest

from plugboard.connector.channel import Channel
from plugboard.connector.channel_builder import ChannelBuilder, ChannelBuilderRegistry


class MyChannel(Channel):
    def __init__(self, a: int, **kwargs: dict[str, _t.Any]) -> None:
        self.a = a
        self.kwargs = kwargs

    async def send(self, msg: int) -> None:
        return

    async def recv(self) -> int:
        return 0


class MyChannelBuilder(ChannelBuilder):
    channel_cls = MyChannel


def test_channel_builder_registry() -> None:
    """Tests the `ChannelBuilderRegistry`."""
    # Register the test channel builder
    assert ChannelBuilderRegistry.get(MyChannel) == MyChannelBuilder


@pytest.mark.anyio
async def test_channel_builder() -> None:
    """Tests the `ChannelBuilder`."""
    channel1 = MyChannelBuilder().build(a=1)
    # Check that the channel was built correctly
    assert isinstance(channel1, MyChannel)
    assert channel1.a == 1
    assert channel1.kwargs == {}
    channel2 = MyChannelBuilder().build(a=2, b=3)
    # Check that the channel was built correctly
    assert isinstance(channel2, MyChannel)
    assert channel2.a == 2
    assert channel2.kwargs == {"b": 3}
