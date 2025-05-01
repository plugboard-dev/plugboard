"""Provides a RabbitMQ channel for sending and receiving messages."""

from __future__ import annotations

import asyncio
from random import random
import typing as _t

from aio_pika import (
    DeliveryMode,
    ExchangeType,
    Message,
)
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
    AbstractRobustConnection,
)
from that_depends import Provide, inject

from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import DI


class RabbitMQChannel(SerdeChannel):
    """`RabbitMQ` channel for sending and receiving messages via RabbitMQ AMQP broker."""

    def __init__(
        self,
        *args: _t.Any,
        send_exchange: _t.Optional[AbstractExchange] = None,
        recv_queue: _t.Optional[AbstractQueue] = None,
        topic: str = "",
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._send_exchange: _t.Optional[AbstractExchange] = send_exchange
        self._recv_queue: _t.Optional[AbstractQueue] = recv_queue
        self._is_send_closed = send_exchange is None
        self._is_recv_closed = recv_queue is None
        self._topic: str = topic

    async def send(self, msg: bytes) -> None:
        """Send a message to the RabbitMQ channel."""
        if self._send_exchange is None:
            raise RuntimeError("Send exchange is not initialized.")
        msg_out = Message(body=msg, delivery_mode=DeliveryMode.PERSISTENT)
        await self._send_exchange.publish(msg_out, routing_key=self._topic)

    async def recv(self) -> bytes:
        """Receive a message from the RabbitMQ channel."""
        if self._recv_queue is None:
            raise RuntimeError("Receive queue is not initialized.")
        # TODO : Observed ~10% time that the timeout is not respected. Instead multiple `get`
        #      : calls are made within a few ms. Try to create an MRE and raise issue on
        #      : https://github.com/mosquito/aio-pika/issues
        # import time
        # for _ in range(3):
        #     print(f"{time.monotonic()} - Waiting for message ...")
        while True:
            # Jitter requests to avoid thundering herd problem
            timeout = 20.0 + random() * 5.0  # noqa: S311 (non-cryptographic usage)
            if (msg_in := await self._recv_queue.get(timeout=timeout, fail=False)) is not None:
                break
        await msg_in.ack()
        return msg_in.body

    async def close(self) -> None:
        """Closes the `RabbitMQChannel`."""
        if self._send_exchange is not None:
            await super().close()
            # TODO : Type annotations in aio-pika make no sense. Raise issue on repo.
            await self._send_exchange.channel.close()  # type: ignore
        self._is_send_closed = True
        self._is_recv_closed = True


class RabbitMQConnector(Connector):
    """`RabbitMQConnector` connects components via RabbitMQ AMQP broker."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic: str = str(self.spec.source)
        self._exchange_type: ExchangeType = (
            ExchangeType.FANOUT if self.spec.mode == ConnectorMode.PUBSUB else ExchangeType.DIRECT
        )
        self._send_channel: _t.Optional[RabbitMQChannel] = None
        self._recv_channel: _t.Optional[RabbitMQChannel] = None

    @inject
    async def connect_send(
        self, rabbitmq_conn: AbstractRobustConnection = Provide[DI.rabbitmq_conn]
    ) -> RabbitMQChannel:
        """Returns a `RabbitMQ` channel for sending messages."""
        if self._send_channel is not None:
            return self._send_channel

        channel = await rabbitmq_conn.channel()
        exchange = await self._declare_exchange(channel)

        self._send_channel = RabbitMQChannel(send_exchange=exchange, topic=self._topic)
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return self._send_channel

    @inject
    async def connect_recv(
        self, rabbitmq_conn: AbstractRobustConnection = Provide[DI.rabbitmq_conn]
    ) -> RabbitMQChannel:
        """Returns a `RabbitMQ` channel for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel

        channel = await rabbitmq_conn.channel()
        await self._declare_exchange(channel)
        queue = await self._declare_queue(channel)

        self._recv_channel = RabbitMQChannel(recv_queue=queue, topic=self._topic)
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return self._recv_channel

    async def _declare_exchange(self, channel: AbstractChannel) -> AbstractExchange:
        """Declares an exchange on the RabbitMQ channel."""
        return await channel.declare_exchange(self._topic, self._exchange_type, durable=True)

    async def _declare_queue(self, channel: AbstractChannel) -> AbstractQueue:
        """Declares a queue on the RabbitMQ channel."""
        await channel.set_qos(prefetch_count=1)
        queue_name = self._topic if self.spec.mode != ConnectorMode.PUBSUB else None
        queue_auto_delete = self.spec.mode == ConnectorMode.PUBSUB
        queue = await channel.declare_queue(queue_name, auto_delete=queue_auto_delete, durable=True)
        await queue.bind(self._topic, routing_key=self._topic)
        return queue
