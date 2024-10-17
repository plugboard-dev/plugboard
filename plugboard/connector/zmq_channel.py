"""Provides ZMQChannel for use in multiprocessing environments."""

import asyncio
from multiprocessing import Manager
import typing as _t

import zmq
import zmq.asyncio

from plugboard.connector.channel import SerdeChannel


ZMQ_ADDR = r"tcp://127.0.0.1"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Instantiates `ZMQChannel`."""
        super().__init__(*args, **kwargs)
        self._manager = Manager()
        self._port = self._manager.Value("i", 0)
        self._context: _t.Optional[zmq.asyncio.Context] = None
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = None

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if not self._context:
            self._context = zmq.asyncio.Context()
            self._send_socket = self._context.socket(zmq.PUSH)
            self._send_socket.bind(self.addr)
            port = self._send_socket.bind_to_random_port(ZMQ_ADDR)
            self._port.value = port
        await self._socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if not self._context:
            self._context = zmq.asyncio.Context()
            # Wait for port to be established by the sender
            while not self._port.value:
                await asyncio.sleep(0.1)
            self._recv_socket.connect(f"{ZMQ_ADDR}:{self._port.value}")
        return await self._socket.recv()
