"""Provides ZMQChannel for use in multiprocessing environments."""

import asyncio
from multiprocessing.managers import SyncManager
import random
import typing as _t

import inject
import zmq
import zmq.asyncio

from plugboard.connector.channel import Channel
from plugboard.connector.channel_builder import ChannelBuilder
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.utils import gen_rand_str


ZMQ_ADDR = r"tcp://127.0.0.1"
ZMQ_CONFIRM_MSG = "__PLUGBOARD_CHAN_CONFIRM_MSG__"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(  # noqa: D417
        self, *args: _t.Any, manager: SyncManager, maxsize: int = 2000, **kwargs: _t.Any
    ) -> None:
        """Instantiates `ZMQChannel`.

        Uses ZeroMQ to provide communication between components on different
        processes. Note that maxsize is not a hard limit because the operating
        system will buffer TCP messages before they reach the channel.

        Args:
            manager: A multiprocessing manager.
            maxsize: Queue maximum item capacity, defaults to 2000.
        """
        super().__init__(*args, **kwargs)
        self._port = manager.Value("i", 0)
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._send_hwm = max(self._maxsize // 2, 1)
        self._recv_hwm = max(self._maxsize - self._send_hwm, 1)
        self._confirm_msg = f"{ZMQ_CONFIRM_MSG}:{gen_rand_str()}".encode()
        # Random poll interval to avoid spikes in activity when multiple channels are created
        self._poll_interval = random.uniform(0.09, 0.11)

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if self._send_socket is None:
            context = zmq.asyncio.Context.instance()
            self._send_socket = context.socket(zmq.PUSH)
            self._send_socket.setsockopt(zmq.SNDHWM, self._send_hwm)
            port = self._send_socket.bind_to_random_port(ZMQ_ADDR)
            self._port.value = port
            await self._send_socket.send(self._confirm_msg)

        await self._send_socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if self._recv_socket is None:
            context = zmq.asyncio.Context.instance()
            self._recv_socket = context.socket(zmq.PULL)
            self._recv_socket.setsockopt(zmq.RCVHWM, self._recv_hwm)
            # Wait for the port to be set by the send socket
            while not self._port.value:
                await asyncio.sleep(self._poll_interval)
            self._recv_socket.connect(f"{ZMQ_ADDR}:{self._port.value}")
            msg = await self._recv_socket.recv()
            if msg != self._confirm_msg:
                raise ChannelSetupError("Channel confirmation message mismatch")

        return await self._recv_socket.recv()


class ZMQChannelBuilder(ChannelBuilder):
    """`ZMQChannelBuilder` builds `ZMQChannel` objects."""

    channel_cls = ZMQChannel

    @inject.params(manager=SyncManager)
    def build(self, *args: _t.Any, manager: SyncManager, **kwargs: _t.Any) -> Channel:  # noqa: D417
        """Builds a `Channel` object.

        Args:
            manager: A multiprocessing manager.
        """
        return self.channel_cls(*args, manager=manager, **kwargs)
