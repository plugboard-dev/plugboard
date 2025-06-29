"""Provides ZMQChannel for use in multiprocessing environments."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import typing as _t

from that_depends import Provide, inject
import zmq
import zmq.asyncio

from plugboard._zmq.zmq_proxy import ZMQ_ADDR, ZMQProxy, create_socket, zmq_sockopts_t
from plugboard.connector.connector import Connector
from plugboard.connector.serde_channel import SerdeChannel
from plugboard.exceptions import ChannelSetupError
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import DI, Settings


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
            self._send_socket = None
        if self._recv_socket is not None:
            self._recv_socket.close()
            self._recv_socket = None
        self._is_send_closed = True
        self._is_recv_closed = True


class _ZMQConnector(Connector, ABC):
    """`_ZMQConnector` connects components using `ZMQChannel`."""

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

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._send_channel: _t.Optional[ZMQChannel] = None
        self._recv_channel: _t.Optional[ZMQChannel] = None

        # Socket to receive sender address from sender
        self._sender_rep_socket = create_socket(zmq.REP, [])
        self._sender_rep_socket_port = self._sender_rep_socket.bind_to_random_port("tcp://*")
        self._sender_rep_socket_addr = f"{self._zmq_address}:{self._sender_rep_socket_port}"
        self._sender_req_lock = asyncio.Lock()
        self._sender_addr: _t.Optional[str] = None

        # Socket to send sender address to receiver
        self._receiver_rep_socket = create_socket(zmq.REP, [])
        self._receiver_rep_socket_port = self._receiver_rep_socket.bind_to_random_port("tcp://*")
        self._receiver_rep_socket_addr = f"{self._zmq_address}:{self._receiver_rep_socket_port}"
        self._receiver_req_lock = asyncio.Lock()

        self._exchange_addr_task = asyncio.create_task(self._exchange_address())
        _zmq_exchange_addr_tasks.add(self._exchange_addr_task)

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in (
            "_sender_rep_socket",
            "_sender_req_lock",
            "_receiver_rep_socket",
            "_receiver_req_lock",
            "_push_socket",
            "_exchange_addr_task",
            "_send_channel",
            "_recv_channel",
        ):
            if attr in state:
                del state[attr]
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._send_channel = None
        self._recv_channel = None

    async def _exchange_address(self) -> None:
        async def _handle_sender_requests() -> None:
            async with self._sender_req_lock:
                sender_request = await self._sender_rep_socket.recv_json()
                if (sender_addr := sender_request.get("sender_address")) is None:
                    await self._sender_rep_socket.send_json({"success": False})
                else:
                    self._sender_addr = sender_addr
                await self._sender_rep_socket.send_json({"success": True})

                while True:
                    await self._sender_rep_socket.recv_json()
                    await self._sender_rep_socket.send_json({"success": False})

        async def _handle_receiver_requests() -> None:
            while self._sender_addr is None:
                await asyncio.sleep(0.5)
            while True:
                async with self._receiver_req_lock:
                    await self._receiver_rep_socket.recv()
                    await self._receiver_rep_socket.send(self._sender_addr.encode())

        async with asyncio.TaskGroup() as tg:
            tg.create_task(_handle_sender_requests())
            tg.create_task(_handle_receiver_requests())

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending messages."""
        if self._send_channel is not None:
            return self._send_channel
        send_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, self._maxsize)])
        send_port = send_socket.bind_to_random_port("tcp://*")
        send_addr = f"{self._zmq_address}:{send_port}"

        sender_req_socket = create_socket(zmq.REQ, [])
        sender_req_socket.connect(self._sender_rep_socket_addr)
        await sender_req_socket.send_json({"sender_address": send_addr})
        resp = await sender_req_socket.recv_json()
        sender_req_socket.close()
        if resp.get("success", False) is not True:
            raise RuntimeError("Failed to setup send socket")

        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        self._send_channel = ZMQChannel(send_socket=send_socket, maxsize=self._maxsize)
        return self._send_channel

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel
        recv_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])

        receiver_req_socket = create_socket(zmq.REQ, [])
        receiver_req_socket.connect(self._receiver_rep_socket_addr)
        await receiver_req_socket.send(b"")
        send_addr = await receiver_req_socket.recv()
        receiver_req_socket.close()

        recv_socket.connect(send_addr.decode())
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

    @inject
    def __init__(
        self, *args: _t.Any, zmq_proxy: ZMQProxy = Provide[DI.zmq_proxy], **kwargs: _t.Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.source)
        self._zmq_proxy = zmq_proxy

        self._send_channel: _t.Optional[ZMQChannel] = None
        self._recv_channel: _t.Optional[ZMQChannel] = None

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        for attr in ("_send_channel", "_recv_channel"):
            if attr in state:
                del state[attr]
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._send_channel = None
        self._recv_channel = None

    async def connect_send(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for sending pubsub messages."""
        if self._send_channel is not None:
            return self._send_channel
        send_socket = create_socket(zmq.PUB, [(zmq.SNDHWM, self._maxsize)])
        send_socket.connect(self._zmq_proxy.xsub_addr)
        self._send_channel = ZMQChannel(
            send_socket=send_socket, topic=self._topic, maxsize=self._maxsize
        )
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return self._send_channel

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving pubsub messages."""
        socket_opts: zmq_sockopts_t = [
            (zmq.RCVHWM, self._maxsize),
            (zmq.SUBSCRIBE, self._topic.encode("utf8")),
        ]
        recv_socket = create_socket(zmq.SUB, socket_opts)
        recv_socket.connect(self._zmq_proxy.xpub_addr)
        recv_channel = ZMQChannel(recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize)
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return recv_channel


class _ZMQPipelineConnectorProxy(_ZMQPubsubConnectorProxy):
    """`_ZMQPipelineConnectorProxy` connects components in pipeline mode using `ZMQChannel`.

    Relies on a ZMQ proxy to handle message routing between components. Messages from publishers are
    proxied to the subscribers through a ZMQ Push socket in a coroutine running on the proxy.
    """

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic = str(self.spec.id)

    async def connect_recv(self) -> ZMQChannel:
        """Returns a `ZMQChannel` for receiving messages."""
        if self._recv_channel is not None:
            return self._recv_channel
        self._push_address = await self._zmq_proxy.add_push_socket(
            self._topic, maxsize=self._maxsize
        )
        recv_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, self._maxsize)])
        recv_socket.connect(self._push_address)
        self._recv_channel = ZMQChannel(
            recv_socket=recv_socket, topic=self._topic, maxsize=self._maxsize
        )
        await asyncio.sleep(0.1)  # Ensure connections established before first send. Better way?
        return self._recv_channel


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
                    zmq_conn_cls: _t.Type[_ZMQConnector] = _ZMQPipelineConnectorProxy
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
