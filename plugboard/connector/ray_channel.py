"""Provides `RayChannel` for use in cluster compute environments."""

import typing as _t

import ray

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import CHAN_MAXSIZE, Channel
from plugboard.connector.channel_builder import ChannelBuilder


class RayChannel(Channel):
    """`RayChannel` enables async data exchange between coroutines on a Ray cluster."""

    def __init__(  # noqa: D417
        self,
        *args: _t.Any,
        maxsize: int = CHAN_MAXSIZE,
        actor_options: _t.Optional[dict] = None,
        **kwargs: _t.Any,
    ):
        """Instantiates `RayChannel`.

        Args:
            maxsize: Optional; Queue maximum item capacity.
            actor_options: Optional; Options to pass to the Ray actor.
        """
        super().__init__(*args, **kwargs)  # type: ignore
        self._actor = ray.remote(**actor_options)(AsyncioChannel).remote(maxsize=maxsize)

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `RayChannel`."""
        return self._actor.maxsize.remote()

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `RayChannel` is closed, `False` otherwise.

        When a `RayChannel` is closed, it can no longer be used to send messages,
        though there may still be some messages waiting to be read.
        """
        return self._actor.is_closed.remote()

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the `RayChannel`."""
        await self._actor.send.remote(item)

    async def recv(self) -> _t.Any:
        """Returns an item received from the `RayChannel`."""
        item = await self._actor.get.remote()
        return item

    async def close(self, force: bool = False, grace_period_s: int = 5) -> None:
        """Closes the `RayChannel` and terminates the underlying actor.

        Args:
            force: Forcefully kill the actor, causing an immediate failure. If `False`, graceful
                actor termination will be attempted first, before falling back to a forceful kill.
            grace_period_s: If force is `False`, how long in seconds to wait for graceful
                termination before falling back to forceful kill.
        """
        if self.actor:
            await self._actor.close.remote()
            if force:
                ray.kill(self._actor, no_restart=True)
            else:
                done_ref = self.actor.__ray_terminate__.remote()
                _, not_done = ray.wait([done_ref], timeout=grace_period_s)
                if not_done:
                    ray.kill(self._actor, no_restart=True)
        self.actor = None


class RayChannelBuilder(ChannelBuilder):
    """`RayChannelBuilder` builds `RayChannel` objects."""

    channel_cls = RayChannel
