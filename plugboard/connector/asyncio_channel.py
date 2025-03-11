"""Provides `AsyncioChannel` class."""

from __future__ import annotations

import asyncio
import typing as _t

from plugboard.connector.channel import CHAN_MAXSIZE, Channel
from plugboard.connector.connector import Connector
from plugboard.schemas.connector import ConnectorMode


class AsyncioChannel(Channel):
    """`AsyncioChannel` enables async data exchange between coroutines on the same host."""

    def __init__(
        self,
        *args: _t.Any,
        maxsize: int = CHAN_MAXSIZE,
        queue: _t.Optional[asyncio.Queue] = None,
        subscribers: _t.Optional[set[asyncio.Queue]] = None,
        **kwargs: _t.Any,
    ):
        """Instantiates `AsyncioChannel`.

        Args:
            maxsize: Optional; Queue maximum item capacity.
            queue: Optional; asyncio.Queue to use for data exchange.
            subscribers: Optional; Set of output asyncio.Queues in pubsub mode.
        """
        super().__init__(*args, **kwargs)
        self._queue: asyncio.Queue = queue or asyncio.Queue(maxsize=maxsize)
        self._subscribers: _t.Optional[set[asyncio.Queue]] = subscribers

    async def send(self, item: _t.Any) -> None:
        """Sends an item through the `Channel`."""
        if self._subscribers is None:
            return await self._queue.put(item)
        async with asyncio.TaskGroup() as tg:
            for queue in self._subscribers:
                tg.create_task(queue.put(item))

    async def recv(self) -> _t.Any:
        """Returns an item received from the `Channel`."""
        item = await self._queue.get()
        self._queue.task_done()
        return item


class AsyncioConnector(Connector):
    """`AsyncioConnector` connects components using `AsyncioChannel`."""

    def __init__(self, *args: _t.Any, maxsize: int = CHAN_MAXSIZE, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._maxsize: int = maxsize
        self._subscribers: _t.Optional[set[asyncio.Queue]] = (
            set() if self.spec.mode == ConnectorMode.PUBSUB else None
        )
        self._send_channel: AsyncioChannel = AsyncioChannel(
            maxsize=self._maxsize, subscribers=self._subscribers
        )

    async def connect_send(self) -> AsyncioChannel:
        """Returns an `AsyncioChannel` for sending messages."""
        return self._send_channel

    async def connect_recv(self) -> AsyncioChannel:
        """Returns an `AsyncioChannel` for receiving messages."""
        if self._subscribers is None:
            return self._send_channel
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        recv_channel = AsyncioChannel(queue=queue, subscribers=None)
        self._subscribers.add(queue)
        return recv_channel
