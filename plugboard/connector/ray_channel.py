"""Provides `RayChannel` for use in cluster compute environments."""

import typing as _t

import ray

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import Channel
from plugboard.connector.channel_builder import ChannelBuilder
from plugboard.utils.ray import build_actor_wrapper


_AsyncioChannelActor = build_actor_wrapper(AsyncioChannel)


class RayChannel(Channel):
    """`RayChannel` enables async data exchange between coroutines on a Ray cluster."""

    def __init__(  # noqa: D417
        self,
        actor_options: _t.Optional[dict] = None,
        **kwargs: _t.Any,
    ):
        """Instantiates `RayChannel`.

        Args:
            actor_options: Optional; Options to pass to the Ray actor. Defaults to {"num_cpus": 1}.
            **kwargs: Additional keyword arguments to pass to the the underlying `Channel`.
        """
        default_options = {"num_cpus": 1}
        actor_options = actor_options or {}
        actor_options = {**default_options, **actor_options}
        self._actor = ray.remote(**actor_options)(_AsyncioChannelActor).remote(**kwargs)

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
