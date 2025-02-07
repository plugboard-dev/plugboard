"""Provides ZMQChannel for use in multiprocessing environments."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import multiprocessing
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

ZMQ_ADDR: str = r"tcp://127.0.0.1"
ZMQ_CONFIRM_MSG: str = "__PLUGBOARD_CHAN_CONFIRM_MSG__"
_zmq_sockopts_t: _t.TypeAlias = list[tuple[int, int | bytes | str]]

# Collection of poll tasks for ZMQ channels required to create strong refs to polling tasks
# to avoid destroying tasks before they are done on garbage collection. Is there a better way?
_zmq_poller_tasks: set[asyncio.Task] = set()


class ZMQChannel(SerdeChannel):
    """`ZMQChannel` enables data exchange between processes using ZeroMQ."""

    def __init__(  # noqa: D417
        self,
        *args: _t.Any,
        send_socket: _t.Optional[zmq.asyncio.Socket] = None,
        recv_socket: _t.Optional[zmq.asyncio.Socket] = None,
        topic: str = "",
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
            send_socket: Optional; The ZeroMQ socket for sending messages.
            recv_socket: Optional; The ZeroMQ socket for receiving messages.
            topic: Optional; The topic for the `ZMQChannel`, defaults to an empty string.
                Only relevant in the case of pub-sub mode channels.
            maxsize: Optional; Queue maximum item capacity, defaults to 2000.
        """
        super().__init__(*args, **kwargs)
        self._send_socket: _t.Optional[zmq.asyncio.Socket] = send_socket
        self._recv_socket: _t.Optional[zmq.asyncio.Socket] = recv_socket
        self._is_send_closed = send_socket is None
        self._is_recv_closed = recv_socket is None
        self._send_hwm = max(maxsize // 2, 1)
        self._recv_hwm = max(maxsize - self._send_hwm, 1)
        self._topic = topic.encode("utf8")

    async def send(self, msg: bytes) -> None:
        """Sends a message through the `ZMQChannel`.

        Args:
            msg: The message to be sent through the `ZMQChannel`.
        """
        if self._send_socket is None:
            raise ChannelSetupError("Send socket is not initialized")
        await self._send_socket.send_multipart([self._topic, msg])

    async def recv(self) -> bytes:
        """Receives a message from the `ZMQChannel` and returns it."""
        if self._recv_socket is None:
            raise ChannelSetupError("Recv socket is not initialized")
        _, msg = await self._recv_socket.recv_multipart()
        return msg

    async def close(self) -> None:
        """Closes the `ZMQChannel`."""
        if self._send_socket is not None:
            await super().close()
            self._send_socket.close()
        if self._recv_socket is not None:
            self._recv_socket.close()
        self._is_send_closed = True
        self._is_recv_closed = True


class _ZMQConnector(Connector, ABC):
    """`_ZMQConnector` connects components using `ZMQChannel`."""

    # FIXME : If multiple workers call `connect_send` they will each see `_send_channel` null
    #       : on first call and create a new channel. This will lead to multiple channels.
    #       : This code only works for the special case of exactly one sender and one receiver
    #       : per ZMQConnector.

    def __init__(
        self, *args: _t.Any, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000, **kwargs: _t.Any
    ) -> None:
        super().__init__(*args, **kwargs)
        # Use a Ray queue to ensure sync ZMQ port number
        self._zmq_address = zmq_address
        self._maxsize = maxsize

    @abstractmethod
    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        pass

    @abstractmethod
    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        pass


class _ZMQPipelineConnector(_ZMQConnector):
    """`_ZMQPipelineConnector` connects components in pipeline mode using `ZMQChannel`."""

    @depends_on_optional("ray")
    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._ray_queue = Queue(maxsize=1)
        self._send_channel: _t.Optional[ZMQChannel] = None
        self._recv_channel: _t.Optional[ZMQChannel] = None
        self._confirm_msg = f"{ZMQ_CONFIRM_MSG}:{gen_rand_str()}".encode()

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        if self._send_channel is not None:
            return self._send_channel
        send_socket = _create_socket(zmq.PUSH, [(zmq.SNDHWM, self._maxsize)])
        port = send_socket.bind_to_random_port("tcp://*")
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
        recv_socket.connect(f"{self._zmq_address}:{port}")
        msg = await recv_socket.recv()
        if msg != self._confirm_msg:
            raise ChannelSetupError("Channel confirmation message mismatch")
        self._recv_channel = ZMQChannel(recv_socket=recv_socket, maxsize=self._maxsize)
        return self._recv_channel


class _ZMQPubsubConnector(_ZMQConnector):
    """`_ZMQPubsubConnector` connects components in pubsub mode using `ZMQChannel`."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.source)
        self._xsub_socket = _create_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)])
        self._xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")
        self._xpub_socket = _create_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)])
        self._xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")
        self._poller = zmq.asyncio.Poller()
        self._poller.register(self._xsub_socket, zmq.POLLIN)
        self._poller.register(self._xpub_socket, zmq.POLLIN)
        self._poll_task = asyncio.create_task(self._poll())
        _zmq_poller_tasks.add(self._poll_task)

    async def _poll(self) -> None:
        poll_fn, xps, xss = self._poller.poll, self._xpub_socket, self._xsub_socket
        try:
            while True:
                events = dict(await poll_fn())
                if xps in events:
                    await xss.send_multipart(await xps.recv_multipart())
                if xss in events:
                    await xps.send_multipart(await xss.recv_multipart())
        finally:
            xps.close(linger=0)
            xss.close(linger=0)

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending pubsub messages."""
        send_socket = _create_socket(zmq.PUB, [(zmq.SNDHWM, self._maxsize)])
        send_socket.connect(f"{self._zmq_address}:{self._xsub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(send_socket=send_socket, topic=self._topic, maxsize=self._maxsize)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving pubsub messages."""
        socket_opts: _zmq_sockopts_t = [
            (zmq.RCVHWM, self._maxsize),
            (zmq.SUBSCRIBE, self._topic.encode("utf8")),
        ]
        recv_socket = _create_socket(zmq.SUB, socket_opts)
        recv_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


class _ZMQProxy(multiprocessing.Process):
    def __init__(self, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000) -> None:
        super().__init__()
        self._maxsize = maxsize
        self._pull_socket = _create_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        port = self._pull_socket.bind_to_random_port("tcp://*")
        self._pull_socket_addr = f"{zmq_address}:{port}"
        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None

    async def get_proxy_ports(self) -> tuple[int, int]:
        """Returns tuple of form (xsub port, xpub port) for the ZMQ proxy."""
        global _ZMQ_PROXY_LOCK
        async with _ZMQ_PROXY_LOCK:
            if self._xsub_port is None or self._xpub_port is None:
                ports_msg = await self._pull_socket.recv_multipart()
                self._xsub_port, self._xpub_port = map(int, ports_msg)
            return self._xsub_port, self._xpub_port

    @staticmethod
    def _create_socket(socket_type: int, socket_opts: _zmq_sockopts_t) -> zmq.Socket:
        ctx = zmq.Context.instance()
        socket = ctx.socket(socket_type)
        for opt, value in socket_opts:
            socket.setsockopt(opt, value)
        return socket

    def run(self) -> None:
        xsub_port, xpub_port = self._create_sockets()
        try:
            ports_msg = [str(xsub_port).encode(), str(xpub_port).encode()]
            self._push_socket.send_multipart(ports_msg)
            zmq.proxy(self._xsub_socket, self._xpub_socket)
        finally:
            self._close()

    def _create_sockets(self) -> _t.Tuple[int, int]:
        """Creates XSUB, XPUB, and PUSH sockets for proxy and returns XSUB and XPUB ports."""
        self._xsub_socket = self._create_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)])
        xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")

        self._xpub_socket = self._create_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)])
        xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")

        self._push_socket = self._create_socket(zmq.PUSH, [(zmq.RCVHWM, 1)])
        self._push_socket.connect(self._pull_socket_addr)

        return xsub_port, xpub_port

    def _close(self) -> None:
        self._xsub_socket.close(linger=0)
        self._xpub_socket.close(linger=0)
        self._push_socket.close(linger=0)


_ZMQ_PROXY: _t.Optional[_ZMQProxy] = None
_ZMQ_PROXY_LOCK: asyncio.Lock = asyncio.Lock()


class _ZMQPubsubConnectorProxy(_ZMQConnector):
    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.source)
        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None

    async def _get_proxy_ports(self) -> tuple[int, int]:
        global _ZMQ_PROXY
        if self._xsub_port is not None and self._xpub_port is not None:
            return self._xsub_port, self._xpub_port
        if _ZMQ_PROXY is None:
            _ZMQ_PROXY = _ZMQProxy(zmq_address=self._zmq_address, maxsize=self._maxsize)
            _ZMQ_PROXY.start()
        self._xsub_port, self._xpub_port = await _ZMQ_PROXY.get_proxy_ports()
        return self._xsub_port, self._xpub_port

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending pubsub messages."""
        await self._get_proxy_ports()
        send_socket = _create_socket(zmq.PUB, [(zmq.SNDHWM, self._maxsize)])
        send_socket.connect(f"{self._zmq_address}:{self._xsub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(send_socket=send_socket, topic=self._topic, maxsize=self._maxsize)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving pubsub messages."""
        await self._get_proxy_ports()
        socket_opts: _zmq_sockopts_t = [
            (zmq.RCVHWM, self._maxsize),
            (zmq.SUBSCRIBE, self._topic.encode("utf8")),
        ]
        recv_socket = _create_socket(zmq.SUB, socket_opts)
        recv_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


def _create_socket(socket_type: int, socket_opts: _zmq_sockopts_t) -> zmq.asyncio.Socket:
    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(socket_type)
    for opt, value in socket_opts:
        socket.setsockopt(opt, value)
    return socket


class ZMQConnector(_ZMQConnector):
    """`ZMQConnector` connects components using `ZMQChannel`."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        match self.spec.mode:
            case ConnectorMode.PIPELINE:
                zmq_conn_cls = _ZMQPipelineConnector
            case ConnectorMode.PUBSUB:
                # FIXME : Remove commented code once WIP work on ZMQ pubsub is complete.
                # zmq_conn_cls = _ZMQPubsubConnectorProxy
                zmq_conn_cls = _ZMQPubsubConnector
            case _:
                raise ValueError(f"Unsupported connector mode: {self.spec.mode}")
        self._zmq_conn_impl: _ZMQConnector = zmq_conn_cls(*args, **kwargs)

    @property
    def zmq_address(self) -> str:
        """The ZMQ address used for communication."""
        return self._zmq_address

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        return await self._zmq_conn_impl.connect_send()

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        return await self._zmq_conn_impl.connect_recv()
