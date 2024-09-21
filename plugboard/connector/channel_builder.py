"""Provides `ChannelBuilderRegistry` to build `Connector` objects."""

from abc import ABC, abstractmethod
import typing as _t

from plugboard.connector.channel import Channel
from plugboard.utils.registry import Registry


class ChannelBuilder(ABC):
    """Base class for `ChannelBuilder` objects."""

    @property
    @abstractmethod
    def channel_cls(self) -> type[Channel]:
        """Returns the `Channel` class that the builder builds."""
        pass

    async def build(self, *args: _t.Any, **kwargs: _t.Any) -> Channel:
        """Builds a `Channel` object."""
        return self.channel_cls(*args, **kwargs)


class ChannelBuilderRegistry(Registry[ChannelBuilder]):
    """A registry of known `ChannelBuilder` classes."""

    @classmethod
    def register(cls, plugboard_class: type[ChannelBuilder], key: type[Channel]) -> None:
        """Register a `ChannelBuilder` for a `Channel` class.

        Args:
            plugboard_class: The `ChannelBuilder` class.
            key: The `Channel` class associated with the `ChannelBuilder`.
        """
        super().register(plugboard_class, key=key)
