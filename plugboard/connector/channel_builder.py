"""Provides `ChannelBuilderRegistry` to build `Connector` objects."""

from abc import ABC, abstractmethod
import typing as _t

from plugboard.connector.channel import Channel


class ChannelBuilder(ABC):
    """Base class for `ChannelBuilder` objects."""

    @abstractmethod
    async def build(self, *args: _t.Any, **kwargs: _t.Any) -> Channel:
        """Builds a `Channel` object."""
        pass


class ChannelBuilderRegistry:
    """A registry of known `ChannelBuilder` classes."""

    channel_builders = {}

    @classmethod
    def register(cls, channel_cls: type[Channel], channel_builder: type[ChannelBuilder]):
        """Register a `ChannelBuilder` for a `Channel` class.

        Args:
            channel_cls: The `Channel` class.
            channel_builder: The `ChannelBuilder` class.
        """
        cls.channel_builders[channel_cls] = channel_builder

    @classmethod
    def get_channel_builder(cls, channel_cls: type[Channel]):
        """Returns a `ChannelBuilder` the specified `Channel` class."""
        return cls.channel_builders[channel_cls]
