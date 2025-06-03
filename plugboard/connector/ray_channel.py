"""Provides `RayChannel` for use in cluster compute environments."""

import typing as _t

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import Channel
from plugboard.connector.connector import Connector
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import build_actor_wrapper, depends_on_optional


try:
    import ray
except ImportError:  # pragma: no cover
    pass

_AsyncioChannelActor = build_actor_wrapper(AsyncioChannel)


class RayChannel(Channel):
    """`RayChannel` enables async data exchange between coroutines on a Ray cluster."""

    @depends_on_optional("ray")
    def __init__(  # noqa: D417
        self,
        actor_options: _t.Optional[dict] = None,
        **kwargs: _t.Any,
    ):
        """Instantiates `RayChannel`.

        Args:
            actor_options: Optional; Options to pass to the Ray actor. Defaults to {"num_cpus": 0}.
            **kwargs: Additional keyword arguments to pass to the the underlying `Channel`.
        """
        default_options = {"num_cpus": 0}
        actor_options = actor_options or {}
        actor_options = {**default_options, **actor_options}
        self._actor = ray.remote(**actor_options)(_AsyncioChannelActor).remote(**kwargs)

    @property
    def maxsize(self) -> int:
        """Returns the message capacity of the `RayChannel`."""
        return self._actor.getattr.remote("maxsize")  # type: ignore

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `RayChannel` is closed, `False` otherwise.

        When a `RayChannel` is closed, it can no longer be used to send messages,
        though there may still be some messages waiting to be read.
        """
        return self._actor.getattr.remote("is_closed")  # type: ignore

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the `RayChannel`."""
        await self._actor.send.remote(item)  # type: ignore

    async def recv(self) -> _t.Any:
        """Returns an item received from the `RayChannel`."""
        return await self._actor.recv.remote()  # type: ignore

    async def close(self) -> None:
        """Closes the `RayChannel` and terminates the underlying actor."""
        await self._actor.close.remote()  # type: ignore


class RayConnector(Connector):
    """`RayConnector` connects components using `RayChannel`."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        if self.spec.mode != ConnectorMode.PIPELINE:
            raise ValueError("RayConnector only supports `PIPELINE` type connections.")
        self._channel = RayChannel()

    async def connect_send(self) -> RayChannel:
        """Returns a `RayChannel` for sending messages."""
        return self._channel

    async def connect_recv(self) -> RayChannel:
        """Returns a `RayChannel` for receiving messages."""
        return self._channel
