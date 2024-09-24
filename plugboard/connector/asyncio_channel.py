"""Provides `AsyncioChannel` class."""

from asyncio import Queue
import typing as _t

from plugboard.connector.channel import CHAN_MAXSIZE, Channel
from plugboard.connector.channel_builder import ChannelBuilder


class AsyncioChannel(Channel):
    """`AsyncioChannel` enables async data exchange between coroutines on the same host."""

    def __init__(self, *args: _t.Any, maxsize: int = CHAN_MAXSIZE, **kwargs: _t.Any):  # noqa: D417
        """Instantiates `AsyncioChannel`.

        Args:
            maxsize: Optional; Queue maximum item capacity.
        """
        super().__init__(*args, **kwargs)  # type: ignore
        self._queue: Queue = Queue(maxsize=maxsize)

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the `Channel`."""
        await self._queue.put(item)

    async def recv(self) -> _t.Any:
        """Returns an item received from the `Channel`."""
        item = await self._queue.get()
        self._queue.task_done()
        return item


class AsyncioChannelBuilder(ChannelBuilder):
    """`AsyncioChannelBuilder` builds `AsyncioChannel` objects."""

    channel_cls = AsyncioChannel
