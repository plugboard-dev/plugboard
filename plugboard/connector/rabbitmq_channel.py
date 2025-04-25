"""Provides a RabbitMQ channel for sending and receiving messages."""

from __future__ import annotations

import typing as _t

import aio_pika
from that_depends import Provide, inject

from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.utils import DI


class RabbitMQChannel(SerdeChannel):
    """`RabbitMQ` channel for sending and receiving messages via RabbitMQ AMQP broker."""

    def __init__(
        self,
        *args: _t.Any,
        send_channel: _t.Optional[aio_pika.RobustChannel] = None,
        recv_channel: _t.Optional[aio_pika.RobustChannel] = None,
        topic: str = "",
        **kwargs: _t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._send_channel: _t.Optional[aio_pika.RobustChannel] = send_channel
        self._recv_channel: _t.Optional[aio_pika.RobustChannel] = recv_channel
        self._recv_queue: _t.Optional[aio_pika.Queue] = None
        self._is_send_closed = send_channel is None
        self._is_recv_closed = recv_channel is None
        self._topic: str = topic

    async def send(self, msg: bytes) -> None:
        """Send a message to the RabbitMQ channel."""
        if self._send_channel is None:
            raise RuntimeError("Send channel is not initialized.")
        await self._send_channel.default_exchange.publish(
            aio_pika.Message(body=msg),
            routing_key=self._topic,
        )

    async def recv(self) -> bytes:
        """Receive a message from the RabbitMQ channel."""
        if self._recv_channel is None:
            raise RuntimeError("Receive channel is not initialized.")
        if self._recv_queue is None:
            self._recv_queue = await self._recv_channel.declare_queue(self._topic, auto_delete=True)
            await self._recv_channel.default_exchange.bind(
                self._recv_queue,
                routing_key=self._topic,
            )
        msg = await self._recv_queue.get()
        await self._recv_queue.ack(msg)
        return msg.body

    async def close(self) -> None:
        """Closes the `RabbitMQChannel`."""
        if self._recv_channel is not None and self._recv_queue is not None:
            await self._recv_queue.unbind(
                self._recv_channel.default_exchange, routing_key=self._topic
            )
            await self._recv_queue.delete()
        self._is_send_closed = True
        self._is_recv_closed = True


class RabbitMQConnector(Connector):
    """`RabbitMQConnector` connects components via RabbitMQ AMQP broker."""

    def __init__(self, *args: _t.Any, rabbitmq_address: str, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._rabbitmq_address: str = rabbitmq_address
        self._topic: str = str(self.spec.source)

        self._send_channel: _t.Optional[RabbitMQChannel] = None
        self._recv_channel: _t.Optional[RabbitMQChannel] = None

    @inject
    async def connect_send(
        self, rabbitmq_conn: aio_pika.RobustConnection = Provide[DI.rabbitmq_conn]
    ) -> RabbitMQChannel:
        """Returns a `RabbitMQ` channel for sending messages."""
        if self._send_channel is not None:
            return self._send_channel
        channel = await rabbitmq_conn.channel()
        self._send_channel = RabbitMQChannel(send_channel=channel)
        return self._send_channel

    @inject
    async def connect_recv(
        self, rabbitmq_conn: aio_pika.RobustConnection = Provide[DI.rabbitmq_conn]
    ) -> RabbitMQChannel:
        """Returns a `RabbitMQ` channel for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel
        channel = await rabbitmq_conn.channel()
        self._recv_channel = RabbitMQChannel(recv_channel=channel)
        return self._recv_channel
