"""Provides ZMQChannel for use in multiprocessing environments."""

import typing as _t

import zmq
import zmq.asyncio
from zmq.devices import ProcessDevice

from plugboard.connector.channel import SerdeChannel


ZMQ_ADDR = r"tcp://127.0.0.1"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Instantiates `ZMQChannel`."""
        super().__init__(*args, **kwargs)
        device = ProcessDevice(zmq.QUEUE, zmq.PULL, zmq.PUSH)
        self._port_send = device.bind_in_to_random_port(ZMQ_ADDR)
        self._port_recv = device.bind_out_to_random_port(ZMQ_ADDR)
        self._context: _t.Optional[zmq.asyncio.Context] = None
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = None
        # Run ZeroMQ Queue device in a background process
        device.start()

    @property
    def send_socket(self) -> zmq.asyncio.Socket:
        """Returns socket for sending messages through the `ZMQChannel`."""
        if not self._send_socket:
            self._context = zmq.asyncio.Context()
            self._send_socket = self._context.socket(zmq.PUSH)
            self._send_socket.connect(f"{self.addr}:{self._port_send}")
        return self._send_socket

    @property
    def recv_socket(self) -> zmq.asyncio.Socket:
        """Returns socket for receiving messages through the `ZMQChannel`."""
        if not self._recv_socket:
            self._context = zmq.asyncio.Context()
            self._recv_socket = self._context.socket(zmq.PULL)
            self._recv_socket.connect(f"{self.addr}:{self._port_recv}")
        return self._recv_socket

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        await self.send_socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        return await self.recv_socket.recv()
