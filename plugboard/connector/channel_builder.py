"""Provides `ChannelBuilderRegistry` to build `Connector` objects."""

from abc import ABC
import typing as _t

from plugboard.connector.channel import Channel
from plugboard.utils.registry import Registry


class ChannelBuilder(ABC):
    """Base class for `ChannelBuilder` objects."""

    channel_cls: type[Channel]

    def build(self, *args: _t.Any, **kwargs: _t.Any) -> Channel:
        """Builds a `Channel` object."""
        return self.channel_cls(*args, **kwargs)


class ChannelBuilderRegistry(Registry[ChannelBuilder]):
    """A registry of known `ChannelBuilder` classes."""

    pass
