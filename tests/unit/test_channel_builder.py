"""Unit tests for the `ChannelBuilder` and `ChannelBuilderRegistry` classes."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.connector.channel import Channel
from plugboard.connector.channel_builder import ChannelBuilder, ChannelBuilderRegistry


class TestChannel(Channel):
    def __init__(self, a: int, **kwargs) -> None:
        self.a = a
        self.kwargs = kwargs

    async def send(self, msg: int) -> None:
        pass

    async def recv(self) -> int:
        pass


class TestChannelBuilder(ChannelBuilder):
    channel_cls = TestChannel


def test_channel_builder_registry() -> None:
    """Tests the `ChannelBuilderRegsitry`."""
    # Register the test channel builder
    ChannelBuilderRegistry.register(TestChannel, TestChannelBuilder)
    assert ChannelBuilderRegistry.get_channel_builder(TestChannel) == TestChannelBuilder


@pytest.mark.anyio
async def test_channel_builder() -> None:
    """Tests the `ChannelBuilder`."""
    channel1 = await TestChannelBuilder().build(a=1)
    # Check that the channel was built correctly
    assert isinstance(channel1, TestChannel)
    assert channel1.a == 1
    assert channel1.kwargs == {}
    channel2 = await TestChannelBuilder().build(a=2, b=3)
    # Check that the channel was built correctly
    assert isinstance(channel2, TestChannel)
    assert channel2.a == 2
    assert channel2.kwargs == {"b": 3}
