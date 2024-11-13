"""Provides `RayChannel` for use in cluster compute environments."""

import typing as _t

import ray

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import Channel
from plugboard.connector.channel_builder import ChannelBuilder


class _ChannelActor:
    """Provides a `Channel` inside a Ray actor."""

    def __init__(self, channel_cls: type[Channel], *args: _t.Any, **kwargs: _t.Any) -> None:
        self._channel = channel_cls(*args, **kwargs)

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the channel."""
        await self._channel.send(item)

    async def recv(self) -> _t.Any:
        """Returns an item received from the channel."""
        return await self._channel.recv()

    async def close(self) -> None:
        """Closes the channel."""
        await self._channel.close()

    def getattr(self, name: str) -> _t.Any:
        """Returns attributes from the channel."""
        return getattr(self._channel, name)


class RayChannel(Channel):
    """`RayChannel` enables async data exchange between coroutines on a Ray cluster."""

    def __init__(  # noqa: D417
        self,
        channel_cls: type[Channel] = AsyncioChannel,
        actor_options: _t.Optional[dict] = None,
        **kwargs: _t.Any,
    ):
        """Instantiates `RayChannel`.

        Args:
            channel_cls: The type of `Channel` to use. Defaults to `AsyncioChannel`.
            actor_options: Optional; Options to pass to the Ray actor. Defaults to {"num_cpus": 1}.
            **kwargs: Additional keyword arguments to pass to the the underlying `Channel`.
        """
        default_options = {"num_cpus": 1}
        actor_options = actor_options or {}
        actor_options = {**default_options, **actor_options}
        self._actor = ray.remote(**actor_options)(_ChannelActor).remote(channel_cls, **kwargs)

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `RayChannel`."""
        return self._actor.getattr.remote("maxsize")

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `RayChannel` is closed, `False` otherwise.

        When a `RayChannel` is closed, it can no longer be used to send messages,
        though there may still be some messages waiting to be read.
        """
        return self._actor.getattr.remote("is_closed")

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the `RayChannel`."""
        await self._actor.send.remote(item)

    async def recv(self) -> _t.Any:
        """Returns an item received from the `RayChannel`."""
        return await self._actor.recv.remote()

    async def close(self) -> None:
        """Closes the `RayChannel` and terminates the underlying actor."""
        await self._actor.close.remote()


class RayChannelBuilder(ChannelBuilder):
    """`RayChannelBuilder` builds `RayChannel` objects."""

    channel_cls = RayChannel
