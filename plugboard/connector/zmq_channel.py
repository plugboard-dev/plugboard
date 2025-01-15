"""Provides ZMQChannel for use in multiprocessing environments."""

import typing as _t

from ray.util.queue import Queue
import zmq
import zmq.asyncio

from plugboard.connector.channel_builder import ChannelBuilder
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.utils import depends_on_optional, gen_rand_str


ZMQ_ADDR = r"tcp://127.0.0.1"
ZMQ_CONFIRM_MSG = "__PLUGBOARD_CHAN_CONFIRM_MSG__"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    @depends_on_optional("ray")
    def __init__(  # noqa: D417
        self, *args: _t.Any, maxsize: int = 2000, **kwargs: _t.Any
    ) -> None:
        """Instantiates `ZMQChannel`.

        Uses ZeroMQ to provide communication between components on different
        processes. Note that maxsize is not a hard limit because the operating
        system will buffer TCP messages before they reach the channel. `ZMQChannel`
        provides better performance than `RayChannel`, but is only suitable for use
        on a single host. For multi-host communication, use `RayChannel`.

        Args:
            maxsize: Queue maximum item capacity, defaults to 2000.
        """
        super().__init__(*args, **kwargs)
        # Use a Ray queue to ensure sync ZMQ port number
        self._ray_queue = Queue(maxsize=1)
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = None
        self._send_hwm = max(self._maxsize // 2, 1)
        self._recv_hwm = max(self._maxsize - self._send_hwm, 1)
        self._confirm_msg = f"{ZMQ_CONFIRM_MSG}:{gen_rand_str()}".encode()

    @staticmethod
    def _create_socket(
        socket_type: int, socket_opts: list[tuple[int, int | bytes | str]]
    ) -> zmq.asyncio.Socket:
        ctx = zmq.asyncio.Context.instance()
        socket = ctx.socket(socket_type)
        for opt, value in socket_opts:
            socket.setsockopt(opt, value)
        return socket

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if self._send_socket is None:
            self._send_socket = self._create_socket(zmq.PUSH, [(zmq.SNDHWM, self._send_hwm)])
            port = self._send_socket.bind_to_random_port(ZMQ_ADDR)
            await self._ray_queue.put_async(port)
            await self._send_socket.send(self._confirm_msg)

        await self._send_socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if self._recv_socket is None:
            self._recv_socket = self._create_socket(zmq.PULL, [(zmq.RCVHWM, self._recv_hwm)])
            # Wait for port from the send socket, use random poll interval to avoid spikes
            port = await self._ray_queue.get_async()
            self._recv_socket.connect(f"{ZMQ_ADDR}:{port}")
            msg = await self._recv_socket.recv()
            if msg != self._confirm_msg:
                raise ChannelSetupError("Channel confirmation message mismatch")

        return await self._recv_socket.recv()


class ZMQChannelBuilder(ChannelBuilder):
    """`ZMQChannelBuilder` builds `ZMQChannel` objects."""

    channel_cls = ZMQChannel
