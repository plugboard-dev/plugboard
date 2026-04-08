"""Provides RedisChannel and RedisConnector."""

from __future__ import annotations

import asyncio
import typing as _t

from plugboard_schemas.connector import ConnectorMode
from that_depends import Provide, inject

from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelClosedError
from plugboard.utils import DI, depends_on_optional


try:
    from redis.asyncio import Redis
    from redis.asyncio.client import PubSub
except ImportError:  # pragma: no cover
    pass


class RedisChannel(SerdeChannel):
    """`RedisChannel` for sending and receiving messages via Redis."""

    @depends_on_optional("redis")
    def __init__(
        self,
        *args: _t.Any,
        key: str,
        send_fn: _t.Optional[_t.Callable[[bytes], _t.Awaitable[None]]] = None,
        recv_fn: _t.Optional[_t.Callable[[], _t.Awaitable[bytes]]] = None,
        pubsub: _t.Optional[PubSub] = None,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates a `RedisChannel`.

        Uses Redis to provide communication between components on different processes.
        Requires a Redis server to be running with the URL set in the `REDIS_URL`
        environment variable.

        Args:
            key: The Redis key for the channel.
            send_fn: Optional; A callable for sending messages to the Redis channel.
            recv_fn: Optional; A callable for receiving messages from the Redis channel.
            pubsub: Optional; The Redis `PubSub` instance, used in pub-sub mode.
        """
        super().__init__(*args, **kwargs)
        self._key = key
        self._send_fn = send_fn
        self._recv_fn = recv_fn
        self._pubsub = pubsub

        # Set initial state based on intended usage
        self._is_send_closed = send_fn is None
        self._is_recv_closed = recv_fn is None

    async def send(self, msg: bytes) -> None:
        """Send a message to the Redis channel."""
        if self._is_send_closed or self._send_fn is None:
            raise ChannelClosedError("Channel is closed for sending")
        await self._send_fn(msg)

    async def recv(self) -> bytes:
        """Receive a message from the Redis channel."""
        if self._is_recv_closed or self._recv_fn is None:
            raise ChannelClosedError("Channel is closed for receiving")
        return await self._recv_fn()

    async def close(self) -> None:
        """Closes the `RedisChannel`."""
        # If we are a sender, send the close message (via super().close())
        if not self._is_send_closed:
            await super().close()
            self._is_send_closed = True

        if self._pubsub is not None:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            self._pubsub = None

        self._is_recv_closed = True


class RedisConnector(Connector):
    """`RedisConnector` connects components via Redis."""

    @depends_on_optional("redis")
    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Instantiates a `RedisConnector`.

        Uses Redis to connect components via either pipeline (list-based) or pub-sub
        (channel-based) mode. Requires a Redis server to be running with the URL set
        in the `REDIS_URL` environment variable.
        """
        super().__init__(*args, **kwargs)
        self._topic: str = (
            str(self.spec.source) if self.spec.mode == ConnectorMode.PUBSUB else self.spec.id
        )
        self._send_channel: _t.Optional[RedisChannel] = None
        self._send_channel_lock = asyncio.Lock()
        self._recv_channel: _t.Optional[RedisChannel] = None
        self._recv_channel_lock = asyncio.Lock()

    def __getstate__(self) -> dict:  # pragma: no cover
        state = self.__dict__.copy()
        for attr in ("_send_channel", "_recv_channel", "_send_channel_lock", "_recv_channel_lock"):
            if attr in state:
                del state[attr]
        return state

    def __setstate__(self, state: dict) -> None:  # pragma: no cover
        self.__dict__.update(state)
        self._send_channel = None
        self._send_channel_lock = asyncio.Lock()
        self._recv_channel = None
        self._recv_channel_lock = asyncio.Lock()

    @inject
    async def _get_key(self, job_id: str = Provide[DI.job_id]) -> str:
        return f"{job_id}.{self._topic}"

    @inject
    async def connect_send(
        self, redis_client: Redis | None = Provide[DI.redis_client]
    ) -> RedisChannel:
        """Returns a `RedisChannel` for sending messages."""
        if redis_client is None:
            raise RuntimeError("Redis client not available. Ensure Redis URL is configured.")
        async with self._send_channel_lock:
            if self._send_channel is not None:
                return self._send_channel

            key = await self._get_key()
            send_fn = self._build_send_fn(redis_client, key)
            self._send_channel = RedisChannel(key=key, send_fn=send_fn)
            return self._send_channel

    def _build_send_fn(
        self, redis_client: Redis, key: str
    ) -> _t.Callable[[bytes], _t.Awaitable[None]]:
        if self.spec.mode == ConnectorMode.PIPELINE:

            async def send_fn(msg: bytes) -> None:
                await redis_client.lpush(key, msg)  # type: ignore[misc]
        else:

            async def send_fn(msg: bytes) -> None:
                await redis_client.publish(key, msg)

        return send_fn

    @inject
    async def connect_recv(
        self, redis_client: Redis | None = Provide[DI.redis_client]
    ) -> RedisChannel:
        """Returns a `RedisChannel` for receiving messages."""
        if redis_client is None:
            raise RuntimeError("Redis client not available. Ensure Redis URL is configured.")
        key = await self._get_key()
        if self.spec.mode == ConnectorMode.PIPELINE:
            async with self._recv_channel_lock:
                if self._recv_channel is not None:
                    return self._recv_channel
                recv_fn = self._build_recv_fn(redis_client, key)
                channel = RedisChannel(key=key, recv_fn=recv_fn)
                self._recv_channel = channel
        else:  # ConnectorMode.PUBSUB
            pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(key)
            recv_fn = self._build_recv_fn(redis_client, key, pubsub=pubsub)
            channel = RedisChannel(key=key, recv_fn=recv_fn, pubsub=pubsub)
        return channel

    def _build_recv_fn(
        self, redis_client: Redis, key: str, pubsub: _t.Optional[PubSub] = None
    ) -> _t.Callable[[], _t.Awaitable[bytes]]:
        if self.spec.mode == ConnectorMode.PIPELINE:

            async def recv_fn() -> bytes:
                result = await redis_client.brpop([key], timeout=None)  # type: ignore[misc]
                return result[1]
        else:
            if pubsub is None:
                raise ValueError("PubSub instance required for PUBSUB mode")

            async def recv_fn() -> bytes:
                # NOTE : We use `listen()` here due to non-sensical `get_message()` behaviour with
                #      : `ignore_subscribe_messages=True`.
                #      : See: https://github.com/redis/redis-py/issues/733#issuecomment-1956647495
                message = await asyncio.wait_for(anext(pubsub.listen()), timeout=None)
                return message["data"]

        return recv_fn
