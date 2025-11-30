"""Provides RedisChannel and RedisConnector."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
import typing as _t

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from that_depends import Provide, inject

from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelClosedError
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import DI


class RedisChannel(SerdeChannel):
    """`RedisChannel` for sending and receiving messages via Redis."""

    def __init__(
        self,
        *args: _t.Any,
        redis_client: Redis,
        key: str,
        mode: ConnectorMode,
        pubsub: _t.Optional[PubSub] = None,
        is_sender: bool = False,
        is_receiver: bool = False,
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._redis = redis_client
        self._key = key
        self._mode = mode
        self._pubsub = pubsub

        # Set initial state based on intended usage
        self._is_send_closed = not is_sender
        self._is_recv_closed = not is_receiver

    async def send(self, msg: bytes) -> None:
        """Sends a message to the Redis channel."""
        if self._is_send_closed:
            raise ChannelClosedError("Channel is closed for sending")

        if self._mode == ConnectorMode.PIPELINE:
            await self._redis.lpush(self._key, msg)
        else:
            await self._redis.publish(self._key, msg)

    async def recv(self) -> bytes:
        """Receives a message from the Redis channel."""
        if self._is_recv_closed:
            raise ChannelClosedError("Channel is closed for receiving")

        if self._mode == ConnectorMode.PIPELINE:
            # brpop returns (key, value) tuple
            # timeout=0 blocks indefinitely
            try:
                result = await self._redis.brpop(self._key, timeout=0)
            except Exception as e:
                # Handle connection errors or closure
                if self._is_recv_closed:
                    raise ChannelClosedError("Channel closed") from e
                raise

            if result is None:
                raise ChannelClosedError("Redis connection closed or returned None")
            return result[1]
        else:
            if self._pubsub is None:
                raise RuntimeError("PubSub object not initialized for receiving")

            while not self._is_recv_closed:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is not None:
                    return message["data"]

            raise ChannelClosedError("Channel closed")

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

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic: str = (
            str(self.spec.source) if self.spec.mode == ConnectorMode.PUBSUB else self.spec.id
        )
        self._send_channel: _t.Optional[RedisChannel] = None
        self._send_channel_lock = asyncio.Lock()
        self._recv_channel: _t.Optional[RedisChannel] = None
        self._recv_channel_lock = asyncio.Lock()

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in ("_send_channel", "_recv_channel", "_send_channel_lock", "_recv_channel_lock"):
            if attr in state:
                del state[attr]
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._send_channel = None
        self._send_channel_lock = asyncio.Lock()
        self._recv_channel = None
        self._recv_channel_lock = asyncio.Lock()

    @inject
    async def _get_key(self, job_id: str = Provide[DI.job_id]) -> str:
        return f"{job_id}.{self._topic}"

    @inject
    async def connect_send(self, redis_client: Redis = Provide[DI.redis_client]) -> RedisChannel:
        """Returns a `RedisChannel` for sending messages."""
        async with self._send_channel_lock:
            if self._send_channel is not None:
                return self._send_channel

            key = await self._get_key()
            self._send_channel = RedisChannel(
                redis_client=redis_client,
                key=key,
                mode=self.spec.mode,
                is_sender=True,
                is_receiver=False,
            )
            return self._send_channel

    @inject
    async def connect_recv(self, redis_client: Redis = Provide[DI.redis_client]) -> RedisChannel:
        """Returns a `RedisChannel` for receiving messages."""
        cm = self._recv_channel_lock if self.spec.mode != ConnectorMode.PUBSUB else nullcontext()
        async with cm:
            if self._recv_channel is not None:
                return self._recv_channel

            key = await self._get_key()
            pubsub = None

            if self.spec.mode == ConnectorMode.PUBSUB:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(key)

            channel = RedisChannel(
                redis_client=redis_client,
                key=key,
                mode=self.spec.mode,
                pubsub=pubsub,
                is_sender=False,
                is_receiver=True,
            )

            if self.spec.mode == ConnectorMode.PIPELINE:
                self._recv_channel = channel

            return channel
