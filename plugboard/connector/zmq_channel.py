"""Provides ZMQChannel for use in multiprocessing environments."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import typing as _t

from that_depends import Provide, inject

from plugboard._zmq.zmq_proxy import ZMQ_ADDR, ZMQProxy, create_socket, zmq_sockopts_t
from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import DI, Settings


try:
    import zmq
    import zmq.asyncio
except ImportError:
    pass

ZMQ_CONFIRM_MSG: str = "__PLUGBOARD_CHAN_CONFIRM_MSG__"

# Collection of poll tasks for ZMQ channels required to create strong refs to polling tasks
# to avoid destroying tasks before they are done on garbage collection. Is there a better way?
_zmq_proxy_tasks: set[asyncio.Task] = set()
_zmq_exchange_addr_tasks: set[asyncio.Task] = set()


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

    # TODO : Remove dependence on Ray from ZMQConnector. Introduce separate RayZMQConnector
    #      : for Ray based ZMQChannel. Improve test coverage for Process and Connector combos.

    def __init__(
        self, *args: _t.Any, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000, **kwargs: _t.Any
    ) -> None:
        super().__init__(*args, **kwargs)
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

    # FIXME : If multiple workers call `connect_send` they will each see `_send_channel` null
    #       : on first call and create a new channel. This will lead to multiple channels.
    #       : This code only works for the special case of exactly one sender and one receiver
    #       : per ZMQConnector.

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._send_channel: _t.Optional[ZMQChannel] = None
        self._recv_channel: _t.Optional[ZMQChannel] = None

        # Socket to receive sender address from sender
        self._pull_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        self._pull_socket_port = self._pull_socket.bind_to_random_port("tcp://*")
        self._pull_socket_addr = f"{self._zmq_address}:{self._pull_socket_port}"

        # Socket to send sender address to receiver
        self._push_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, 1)])
        self._push_socket_port = self._push_socket.bind_to_random_port("tcp://*")
        self._push_socket_addr = f"{self._zmq_address}:{self._push_socket_port}"

        self._exchange_addr_task = asyncio.create_task(self._exchange_address())
        _zmq_exchange_addr_tasks.add(self._exchange_addr_task)

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in ("_pull_socket", "_push_socket", "_exchange_addr_task"):
            if attr in state:
                del state[attr]
        return state

    async def _exchange_address(self) -> None:
        sender_address = await self._pull_socket.recv()
        await self._push_socket.send(sender_address)

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        if self._send_channel is not None:
            return self._send_channel
        send_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, self._maxsize)])
        port = send_socket.bind_to_random_port("tcp://*")

        push_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, 1)])
        push_socket.connect(self._pull_socket_addr)
        await push_socket.send(str(port).encode())

        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        self._send_channel = ZMQChannel(send_socket=send_socket, maxsize=self._maxsize)
        return self._send_channel

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel
        recv_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])

        # Wait for port from the send socket, use random poll interval to avoid spikes
        pull_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        pull_socket.connect(self._push_socket_addr)
        port = int(await pull_socket.recv())

        recv_socket.connect(f"{self._zmq_address}:{port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        self._recv_channel = ZMQChannel(recv_socket=recv_socket, maxsize=self._maxsize)
        return self._recv_channel


class _ZMQPubsubConnector(_ZMQConnector):
    """`_ZMQPubsubConnector` connects components in pubsub mode using `ZMQChannel`."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.source)
        self._xsub_socket = create_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)])
        self._xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")
        self._xpub_socket = create_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)])
        self._xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")
        self._poller = zmq.asyncio.Poller()
        self._poller.register(self._xsub_socket, zmq.POLLIN)
        self._poller.register(self._xpub_socket, zmq.POLLIN)
        self._poll_task = asyncio.create_task(self._poll())
        _zmq_proxy_tasks.add(self._poll_task)

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        # Remove non-serializable attributes
        for attr in ("_poller", "_poll_task", "_xsub_socket", "_xpub_socket"):
            if attr in state:
                del state[attr]
        return state

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
        send_socket = create_socket(zmq.PUB, [(zmq.SNDHWM, self._maxsize)])
        send_socket.connect(f"{self._zmq_address}:{self._xsub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(send_socket=send_socket, topic=self._topic, maxsize=self._maxsize)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving pubsub messages."""
        socket_opts: zmq_sockopts_t = [
            (zmq.RCVHWM, self._maxsize),
            (zmq.SUBSCRIBE, self._topic.encode("utf8")),
        ]
        recv_socket = create_socket(zmq.SUB, socket_opts)
        recv_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


class _ZMQPubsubConnectorProxy(_ZMQConnector):
    """`_ZMQPubsubConnectorProxy` acts is a python asyncio based proxy for `ZMQChannel` messages."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.source)
        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None

    @inject
    async def _get_proxy_ports(
        self, zmq_proxy: ZMQProxy = Provide[DI.zmq_proxy]
    ) -> tuple[int, int]:
        if self._xsub_port is not None and self._xpub_port is not None:
            return self._xsub_port, self._xpub_port
        await zmq_proxy.start_proxy(zmq_address=self._zmq_address, maxsize=self._maxsize)
        self._xsub_port, self._xpub_port = await zmq_proxy.get_proxy_ports()
        return self._xsub_port, self._xpub_port

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending pubsub messages."""
        await self._get_proxy_ports()
        send_socket = create_socket(zmq.PUB, [(zmq.SNDHWM, self._maxsize)])
        send_socket.connect(f"{self._zmq_address}:{self._xsub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(send_socket=send_socket, topic=self._topic, maxsize=self._maxsize)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving pubsub messages."""
        await self._get_proxy_ports()
        socket_opts: zmq_sockopts_t = [
            (zmq.RCVHWM, self._maxsize),
            (zmq.SUBSCRIBE, self._topic.encode("utf8")),
        ]
        recv_socket = create_socket(zmq.SUB, socket_opts)
        recv_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


class _ZMQPipelineConnectorV2(_ZMQPubsubConnectorProxy):
    """`_ZMQPipelineConnectorV2` connects components in pipeline mode using `ZMQChannel`.

    Relies on a ZMQ proxy to handle message routing between components. Messages from publishers are
    proxied to the subscribers through a ZMQ Push socket in a coroutine running on the driver.
    """

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.id)

        self._push_socket: zmq.asyncio.Socket = create_socket(
            zmq.PUSH, [(zmq.SNDHWM, self._maxsize)]
        )
        self._push_port: int = self._push_socket.bind_to_random_port("tcp://*")

        self._push_proxy_task: asyncio.Task = asyncio.create_task(self._start_push_proxy())
        _zmq_proxy_tasks.add(self._push_proxy_task)

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in ("_push_socket", "_push_proxy_task"):
            if attr in state:
                del state[attr]
        return state

    async def _start_push_proxy(self) -> None:
        _, xpub_port = await self._get_proxy_ports()

        sub_socket = create_socket(
            zmq.SUB, [(zmq.RCVHWM, self._maxsize), (zmq.SUBSCRIBE, self._topic.encode("utf8"))]
        )
        sub_socket.connect(f"{self._zmq_address}:{xpub_port}")
        try:
            while True:
                msg = await sub_socket.recv_multipart()
                await self._push_socket.send_multipart(msg)
        finally:
            sub_socket.close(linger=0)
            self._push_socket.close(linger=0)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        recv_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])
        recv_socket.connect(f"{self._zmq_address}:{self._push_port}")
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


class _ZMQPipelineConnectorV3(_ZMQPubsubConnectorProxy):
    """`_ZMQPipelineConnectorV3` connects components in pipeline mode using `ZMQChannel`.

    Relies on a ZMQ proxy to handle message routing between components. Messages from publishers are
    proxied to the subscribers through a ZMQ Push socket in a coroutine running on the proxy.
    """

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.id)
        self._push_address: _t.Optional[str] = None
        self._push_address_task = asyncio.create_task(self._get_push_address())
        _zmq_proxy_tasks.add(self._push_address_task)

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in ("_push_address_task",):
            if attr in state:
                del state[attr]
        return state

    @inject
    async def _get_push_address(self, zmq_proxy: ZMQProxy = Provide[DI.zmq_proxy]) -> str:
        await self._get_proxy_ports()
        self._push_address = await zmq_proxy.add_push_socket(self._topic, maxsize=self._maxsize)
        return self._push_address

    async def _wait_for_push_address(self) -> str:
        retries = 0
        while self._push_address is None and retries < 5:
            await asyncio.sleep(0.01)
            retries += 1
        if self._push_address is None:
            raise RuntimeError("Push address not set")
        return self._push_address

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        await self._get_proxy_ports()
        self._push_address = await self._wait_for_push_address()
        recv_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])
        recv_socket.connect(self._push_address)
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)


class ZMQConnector(_ZMQConnector):
    """`ZMQConnector` connects components using `ZMQChannel`."""

    @inject
    def __init__(
        self, *args: _t.Any, settings: Settings = Provide[DI.settings], **kwargs: _t.Any
    ) -> None:
        super().__init__(*args, **kwargs)
        match self.spec.mode:
            case ConnectorMode.PIPELINE:
                if settings.flags.zmq_pubsub_proxy:
                    zmq_conn_cls: _t.Type[_ZMQConnector] = _ZMQPipelineConnectorV3
                else:
                    zmq_conn_cls = _ZMQPipelineConnector
            case ConnectorMode.PUBSUB:
                print(f"{settings=}")
                if settings.flags.zmq_pubsub_proxy:
                    zmq_conn_cls = _ZMQPubsubConnectorProxy
                else:
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
