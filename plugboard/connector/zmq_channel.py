"""Provides ZMQChannel for use in multiprocessing environments."""

import asyncio
import multiprocessing as mp
import typing as _t

import zmq
import zmq.asyncio

from plugboard.connector.channel_builder import ChannelBuilder
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.utils import gen_rand_str


ZMQ_ADDR = r"tcp://127.0.0.1"
ZMQ_CONFIRM_MSG = "__PLUGBOARD_CHAN_CONFIRM_MSG__"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(self, *args: _t.Any, maxsize: int = 2000, **kwargs: _t.Any) -> None:  # noqa: D417
        """Instantiates `ZMQChannel`.

        Uses ZeroMQ to provide communication between components on different
        processes. Note that maxsize is not a hard limit because the operating
        system will buffer TCP messages before they reach the channel.

        Args:
            maxsize: Queue maximum item capacity, defaults to 2000.
        """
        super().__init__(*args, **kwargs)
        self._port = mp.Value("i", 0)
        self._context: _t.Optional[zmq.asyncio.Context] = None
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._send_hwm = maxsize // 2
        self._recv_hwm = maxsize - self._send_hwm
        self._confirm_msg = f"{ZMQ_CONFIRM_MSG}:{gen_rand_str()}".encode()

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if not self._send_socket:
            self._context = zmq.asyncio.Context()
            self._send_socket = self._context.socket(zmq.PUSH)
            self._send_socket.setsockopt(zmq.SNDHWM, self._send_hwm)
            port = self._send_socket.bind_to_random_port(ZMQ_ADDR)
            self._port.value = port
            await self._send_socket.send(self._confirm_msg)

        await self._send_socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if not self._recv_socket:
            self._context = zmq.asyncio.Context()
            self._recv_socket = self._context.socket(zmq.PULL)
            self._recv_socket.setsockopt(zmq.RCVHWM, self._recv_hwm)
            # Wait for port to be established by the sender
            while not self._port.value:
                await asyncio.sleep(0.1)
            self._recv_socket.connect(f"{ZMQ_ADDR}:{self._port.value}")

            # First message should confirm channel setup
            msg = await self._recv_socket.recv()
            if msg != self._confirm_msg:
                raise ChannelSetupError(
                    f"Channel setup not confirmed: got {msg!r}, expected {self._confirm_msg!r}."
                )
        return await self._recv_socket.recv()


class ZMQChannelBuilder(ChannelBuilder):
    """`ZMQChannelBuilder` builds `ZMQChannel` objects."""

    channel_cls = ZMQChannel
