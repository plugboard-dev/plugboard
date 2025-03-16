"""Provides `ZMQProxy` class for proxying ZMQ socket connections with libzmq."""

from __future__ import annotations

import asyncio
import multiprocessing
import typing as _t


try:
    import zmq
    import zmq.asyncio
except ImportError:
    pass

zmq_sockopts_t: _t.TypeAlias = list[tuple[int, int | bytes | str]]
ZMQ_ADDR: str = r"tcp://127.0.0.1"


def create_socket(
    socket_type: int,
    socket_opts: zmq_sockopts_t,
    ctx: _t.Optional[zmq.Context | zmq.asyncio.Context] = None,
) -> zmq.asyncio.Socket:
    """Creates a ZeroMQ socket with the given type and options.

    Args:
        socket_type: The type of socket to create.
        socket_opts: The options to set on the socket.
        ctx: The ZMQ context to use. Uses an async context by default.

    Returns:
        The created ZMQ socket.
    """
    _ctx = ctx or zmq.asyncio.Context.instance()
    socket = _ctx.socket(socket_type)
    for opt, value in socket_opts:
        socket.setsockopt(opt, value)
    return socket


class ZMQProxy(multiprocessing.Process):
    """`ZMQProxy` proxies ZMQ socket connections with libzmq in a separate process.

    This class should be created as a singleton and used to proxy all ZMQ pubsub connections.
    """

    def __init__(self, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000) -> None:
        super().__init__()
        self._zmq_address: str = zmq_address
        self._zmq_proxy_lock: asyncio.Lock = asyncio.Lock()
        self._maxsize: int = maxsize
        self._pull_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        self._pull_socket_port: int = self._pull_socket.bind_to_random_port("tcp://*")
        self._pull_socket_address: str = f"{self._zmq_address}:{self._pull_socket_port}"
        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None
        self._proxy_started: bool = False
        self._push_poller: zmq.asyncio.Poller = zmq.asyncio.Poller()
        self._push_sockets: dict[str, zmq.asyncio.Socket] = {}

        # Socket for requesting push socket creation in the subprocess
        self._socket_req_socket = create_socket(zmq.REQ, [(zmq.RCVHWM, 1)])
        self._socket_req_port: int = 0  # Will be set when the proxy subprocess starts

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        keys_to_delete = (
            "_pull_socket",
            "_zmq_proxy_lock",
            "_push_poller",
            "_push_sockets",
            "_socket_req_socket",
        )
        for key in keys_to_delete:
            if key in state:
                del state[key]
        return state

    async def start_proxy(self, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000) -> None:
        """Starts the ZMQ proxy with the given address and maxsize."""
        async with self._zmq_proxy_lock:
            if self._proxy_started:
                if zmq_address != self._zmq_address:
                    raise RuntimeError("ZMQ proxy already started with different address.")
                return
            self._zmq_address = zmq_address
            self._maxsize = maxsize
            self._pull_socket_address = f"{self._zmq_address}:{self._pull_socket_port}"
            self.start()
            self._proxy_started = True

    async def get_proxy_ports(self) -> tuple[int, int]:
        """Returns tuple of form (xsub port, xpub port) for the ZMQ proxy."""
        if not self._proxy_started:
            raise RuntimeError("ZMQ proxy not started.")
        async with self._zmq_proxy_lock:
            if self._xsub_port is None or self._xpub_port is None:
                ports_msg = await self._pull_socket.recv_multipart()
                # The first two values are xsub_port and xpub_port
                self._xsub_port, self._xpub_port = map(int, ports_msg[:2])
                # If there's a third value, it's the socket_req_port
                if len(ports_msg) > 2:
                    self._socket_req_port = int(ports_msg[2])
                    self._socket_req_socket.connect(f"{self._zmq_address}:{self._socket_req_port}")
            return self._xsub_port, self._xpub_port

    async def add_push_socket(self, topic: str, maxsize: int = 2000) -> str:
        """Adds a push socket for the given pubsub topic and returns the address."""
        if not self._proxy_started or self._xpub_port is None:
            raise RuntimeError("ZMQ proxy xpub port is not set.")
        if self._socket_req_port == 0:
            raise RuntimeError("Socket request port is not set.")

        # Send request to create a push socket in the subprocess
        request = {"action": "create_push_socket", "topic": topic, "maxsize": maxsize}

        # Send the request to the subprocess
        await self._socket_req_socket.send_json(request)

        # Receive the response with the push socket address
        response = await self._socket_req_socket.recv_json()

        if "error" in response:
            raise RuntimeError(f"Failed to create push socket: {response['error']}")

        return response["push_address"]

    def run(self) -> None:
        """Multiprocessing entrypoint to run ZMQ proxy."""
        try:
            asyncio.run(self._run())
        finally:
            self._close()

    async def _run(self) -> None:
        """Async multiprocessing entrypoint to run ZMQ proxy."""
        async with asyncio.TaskGroup() as tg:
            tg.create_task(asyncio.to_thread(self._run_pubsub_proxy))
            tg.create_task(self._handle_socket_requests())
            tg.create_task(self._poll_push_sockets())

    async def _handle_socket_requests(self) -> None:
        """Handles requests to create sockets in the subprocess."""
        # Create a socket to receive socket creation requests
        ctx = zmq.Context.instance()
        self._socket_rep_socket = create_socket(zmq.REP, [], ctx=ctx)
        # This port is passed to the main process via _create_sockets()
        self._socket_rep_socket.bind_to_random_port("tcp://*")

        try:
            while True:
                request = await self._socket_rep_socket.recv_json()
                if request["action"] == "create_push_socket":
                    try:
                        push_address = await self._create_push_socket_in_subprocess(
                            request["topic"], request["maxsize"]
                        )
                        await self._socket_rep_socket.send_json({"push_address": push_address})
                    except Exception as e:
                        await self._socket_rep_socket.send_json({"error": str(e)})
        finally:
            self._socket_rep_socket.close(linger=0)

    async def _create_push_socket_in_subprocess(self, topic: str, maxsize: int) -> str:
        """Creates a push socket in the subprocess and returns its address."""
        # Create the SUB socket to receive messages from the XPUB socket
        sub_socket = create_socket(
            zmq.SUB, [(zmq.RCVHWM, self._maxsize), (zmq.SUBSCRIBE, topic.encode("utf8"))]
        )
        sub_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        self._push_poller.register(sub_socket, zmq.POLLIN)

        # Create the PUSH socket that clients will connect to
        push_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, maxsize)])
        push_port = push_socket.bind_to_random_port("tcp://*")
        push_address = f"{self._zmq_address}:{push_port}"
        self._push_sockets[topic] = push_socket

        return push_address

    async def _poll_push_sockets(self) -> None:
        """Polls push sockets for messages and sends them to the proxy."""
        while True:
            events = dict(await self._push_poller.poll())
            async with asyncio.TaskGroup() as tg:
                for socket in events:
                    tg.create_task(self._handle_push_socket(socket))

    async def _handle_push_socket(self, socket: zmq.asyncio.Socket) -> None:
        msg = await socket.recv_multipart()
        topic = msg[0].decode("utf8")
        push_socket = self._push_sockets[topic]
        await push_socket.send_multipart(msg)

    def _run_pubsub_proxy(self) -> None:
        """Runs the ZMQ proxy for pubsub connections."""
        xsub_port, xpub_port, socket_req_port = self._create_sockets()
        ports_msg = [
            str(xsub_port).encode(),
            str(xpub_port).encode(),
            str(socket_req_port).encode(),
        ]
        self._push_socket.send_multipart(ports_msg)
        zmq.proxy(self._xsub_socket, self._xpub_socket)

    def _create_sockets(self) -> _t.Tuple[int, int, int]:
        """Creates XSUB, XPUB, REP and PUSH sockets for proxy.

        Returns:
            Tuple of (xsub_port, xpub_port, socket_req_port)
        """
        ctx = zmq.Context.instance()
        self._xsub_socket = create_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)], ctx=ctx)
        xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")

        self._xpub_socket = create_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)], ctx=ctx)
        xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")

        self._socket_rep_socket = create_socket(zmq.REP, [], ctx=ctx)
        socket_req_port = self._socket_rep_socket.bind_to_random_port("tcp://*")

        self._push_socket = create_socket(zmq.PUSH, [(zmq.RCVHWM, 1)], ctx=ctx)
        self._push_socket.connect(self._pull_socket_address)

        return xsub_port, xpub_port, socket_req_port

    def _close(self) -> None:
        self._xsub_socket.close(linger=0)
        self._xpub_socket.close(linger=0)
        self._push_socket.close(linger=0)
        if hasattr(self, "_socket_rep_socket"):
            self._socket_rep_socket.close(linger=0)
