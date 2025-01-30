"""Provides ZMQChannel for use in multiprocessing environments."""

import typing as _t

from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import depends_on_optional, gen_rand_str


try:
    from ray.util.queue import Queue
    import zmq
    import zmq.asyncio
except ImportError:
    pass

ZMQ_ADDR = r"tcp://127.0.0.1"
ZMQ_CONFIRM_MSG = "__PLUGBOARD_CHAN_CONFIRM_MSG__"


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(  # noqa: D417
        self,
        *args: _t.Any,
        send_socket: _t.Optional[zmq.asyncio.Socket] = None,
        recv_socket: _t.Optional[zmq.asyncio.Socket] = None,
        maxsize: int = 2000,
        **kwargs: _t.Any,
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
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = send_socket
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = recv_socket
        self._is_send_closed = send_socket is None
        self._is_recv_closed = recv_socket is None
        self._send_hwm = max(maxsize // 2, 1)
        self._recv_hwm = max(maxsize - self._send_hwm, 1)

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if self._send_socket is None:
            raise ChannelSetupError("Send socket is not initialized")
        await self._send_socket.send(msg)

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if self._recv_socket is None:
            raise ChannelSetupError("Recv socket is not initialized")
        return await self._recv_socket.recv()

    async def close(self) -> None:
        """Closes the `ZMQChannel`."""
        if self._send_socket is not None:
            await super().close()
            self._send_socket.close()
        if self._recv_socket is not None:
            self._recv_socket.close()
        self._is_send_closed = True
        self._is_recv_closed = True


class ZMQConnector(Connector):
    """`ZMQConnector` connects components using `ZMQChannel`."""

    # FIXME : If multiple workers call `connect_send` they will each see `_send_channel` null
    #       : on first call and create a new channel. This will lead to multiple channels.
    #       : This code only works for the special case of exactly one sender and one receiver
    #       : per ZMQConnector.

    @depends_on_optional("ray")
    def __init__(self, *args: _t.Any, maxsize: int = 2000, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        if self.spec.mode != ConnectorMode.PIPELINE:
            raise ValueError("ZMQConnector only supports `PIPELINE` type connections.")
        # Use a Ray queue to ensure sync ZMQ port number
        self._ray_queue = Queue(maxsize=1)
        self._maxsize = maxsize
        self._send_channel: _t.Optional[ZMQChannel] = None
        self._recv_channel: _t.Optional[ZMQChannel] = None
        self._confirm_msg = f"{ZMQ_CONFIRM_MSG}:{gen_rand_str()}".encode()

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        if self._send_channel is not None:
            return self._send_channel
        send_socket = _create_socket(zmq.PUSH, [(zmq.SNDHWM, self._maxsize)])
        port = send_socket.bind_to_random_port(ZMQ_ADDR)
        await self._ray_queue.put_async(port)
        await send_socket.send(self._confirm_msg)
        self._send_channel = ZMQChannel(send_socket=send_socket, maxsize=self._maxsize)
        return self._send_channel

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel
        recv_socket = _create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])
        # Wait for port from the send socket, use random poll interval to avoid spikes
        port = await self._ray_queue.get_async()
        self._ray_queue.shutdown()
        recv_socket.connect(f"{ZMQ_ADDR}:{port}")
        msg = await recv_socket.recv()
        if msg != self._confirm_msg:
            raise ChannelSetupError("Channel confirmation message mismatch")
        self._recv_channel = ZMQChannel(recv_socket=recv_socket, maxsize=self._maxsize)
        return self._recv_channel


def _create_socket(
    socket_type: int, socket_opts: list[tuple[int, int | bytes | str]]
) -> zmq.asyncio.Socket:
    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(socket_type)
    for opt, value in socket_opts:
        socket.setsockopt(opt, value)
    return socket
