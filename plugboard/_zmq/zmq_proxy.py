"""Provides `ZMQProxy` class for proxying ZMQ socket connections with libzmq."""

from __future__ import annotations

import asyncio
import multiprocessing
import typing as _t

from pydantic import BaseModel, Field, ValidationError
import zmq
import zmq.asyncio


try:
    from uvloop import run as _asyncio_run
except ImportError:  # pragma: no cover
    from asyncio import run as _asyncio_run

zmq_sockopts_t: _t.TypeAlias = list[tuple[int, int | bytes | str]]
ZMQ_ADDR: str = r"tcp://127.0.0.1"


def create_socket(
    socket_type: int,
    socket_opts: zmq_sockopts_t,
    ctx: _t.Optional[zmq.asyncio.Context] = None,
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


def _create_sync_socket(
    socket_type: int,
    socket_opts: zmq_sockopts_t,
    ctx: _t.Optional[zmq.Context] = None,
) -> zmq.Socket:
    """Creates a ZeroMQ socket with the given type and options.

    Args:
        socket_type: The type of socket to create.
        socket_opts: The options to set on the socket.
        ctx: The ZMQ context to use. Uses an sync context by default.

    Returns:
        The created ZMQ socket.
    """
    _ctx = ctx or zmq.Context.instance()
    socket = _ctx.socket(socket_type)
    for opt, value in socket_opts:
        socket.setsockopt(opt, value)
    return socket


class _PushSocketRequest(BaseModel):
    """Request to create a push socket."""

    topic: str = Field(min_length=3)
    maxsize: int = Field(ge=1)
    reuse: bool = True


class ZMQProxy:
    """`ZMQProxy` proxies ZMQ socket connections with libzmq in a separate process.

    This class should be created as a singleton and used to proxy all ZMQ pubsub connections.
    """

    def __init__(self, zmq_address: str = ZMQ_ADDR, maxsize: int = 2000) -> None:
        self._zmq_address: str = zmq_address
        self._zmq_proxy_lock: asyncio.Lock = asyncio.Lock()
        self._maxsize: int = maxsize
        self._process: _t.Optional[multiprocessing.Process] = None

        # Socket for receiving xsub and xpub ports from the subprocess
        self._pull_socket: zmq.Socket = _create_sync_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        self._pull_socket_port: int = self._pull_socket.bind_to_random_port("tcp://*")
        self._pull_socket_address: str = f"{self._zmq_address}:{self._pull_socket_port}"

        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None
        self._socket_rep_port: _t.Optional[int] = None

        self._proxy_started: bool = False

        self._start_proxy()
        self._get_proxy_ports()
        self._connect_socket_req_socket()

    @property
    def xsub_addr(self) -> str:
        """Returns the XSUB address for the proxy."""
        if not self._proxy_started or self._xsub_port is None:
            raise RuntimeError("ZMQ XSUB port is not set.")
        return f"{self._zmq_address}:{self._xsub_port}"

    @property
    def xpub_addr(self) -> str:
        """Returns the XPUB address for the proxy."""
        if not self._proxy_started or self._xpub_port is None:
            raise RuntimeError("ZMQ XPUB port is not set.")
        return f"{self._zmq_address}:{self._xpub_port}"

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        # Process-specific attributes
        process_attrs = ("_process",)
        # Socket and async objects
        non_serializable = (
            "_pull_socket",
            "_zmq_proxy_lock",
            "_push_poller",
            "_push_sockets",
            "_socket_req_socket",
            "_socket_req_lock",
            "_xsub_socket",
            "_xpub_socket",
            "_socket_rep_socket",
        )
        # Remove all non-serializable attributes
        rm_keys = process_attrs + non_serializable
        for key in rm_keys:
            if key in state:
                del state[key]
        return state

    def __setstate__(self, state: dict) -> None:
        """Restore object state after unpickling in child process."""
        self.__dict__.update(state)
        self._process = None
        if self._socket_rep_port is not None:
            # Recreate push socket request socket in serialised copies of the ZMQProxy object but
            # not in the proxy subprocess started from the driver process when using spawn.
            self._connect_socket_req_socket()

    def _start_proxy(
        self, zmq_address: _t.Optional[str] = None, maxsize: _t.Optional[int] = None
    ) -> None:
        """Starts the ZMQ proxy with the given address and maxsize."""
        if self._proxy_started:
            if zmq_address is not None and zmq_address != self._zmq_address:
                raise RuntimeError("ZMQ proxy already started with different address.")
            return
        self._zmq_address = zmq_address or self._zmq_address
        self._maxsize = maxsize or self._maxsize
        self._pull_socket_address = f"{self._zmq_address}:{self._pull_socket_port}"

        # Start a new process to run the proxy
        self._process = multiprocessing.Process(target=self._run_process)
        self._process.daemon = True
        self._process.start()

        self._proxy_started = True

    def _run_process(self) -> None:
        """Entry point for the child process."""
        try:
            _asyncio_run(self._run())
        finally:  # pragma: no cover
            self._close()

    def _get_proxy_ports(self) -> tuple[int, int, int]:
        """Returns tuple of form (xsub port, xpub port, socket rep port) for the ZMQ proxy."""
        if not self._proxy_started:
            raise RuntimeError("ZMQ proxy not started.")
        if self._xsub_port is None or self._xpub_port is None or self._socket_rep_port is None:
            ports_msg = self._pull_socket.recv_multipart()
            self._xsub_port, self._xpub_port, self._socket_rep_port = map(int, ports_msg)
        return self._xsub_port, self._xpub_port, self._socket_rep_port

    def _connect_socket_req_socket(self) -> None:
        """Connects the REQ socket to the REP socket in the subprocess."""
        if self._socket_rep_port is None:
            raise RuntimeError("ZMQ proxy socket REP port not set.")
        self._socket_req_socket: zmq.asyncio.Socket = create_socket(zmq.REQ, [])
        socket_rep_socket_address: str = f"{self._zmq_address}:{self._socket_rep_port}"
        self._socket_req_socket.connect(socket_rep_socket_address)
        self._socket_req_lock: asyncio.Lock = asyncio.Lock()

    async def add_push_socket(self, topic: str, maxsize: int = 2000) -> str:
        """Adds a push socket for the given pubsub topic and returns the address."""
        if not self._proxy_started or self._xpub_port is None:
            raise RuntimeError("ZMQ proxy xpub port is not set.")

        async with self._socket_req_lock:
            await self._socket_req_socket.send_json({"topic": topic, "maxsize": maxsize})
            response = await self._socket_req_socket.recv_json()

        if "error" in response:
            raise RuntimeError(f"Failed to create push socket: {response['error']}")

        return response["push_address"]

    async def _run(self) -> None:
        """Async multiprocessing entrypoint to run ZMQ proxy."""
        self._push_poller: zmq.asyncio.Poller = zmq.asyncio.Poller()
        self._push_sockets: dict[str, tuple[str, zmq.asyncio.Socket]] = {}

        self._create_proxy_sockets()

        ports_msg = [
            str(self._xsub_port).encode(),
            str(self._xpub_port).encode(),
            str(self._socket_rep_port).encode(),
        ]
        self._push_socket.send_multipart(ports_msg)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(asyncio.to_thread(self._run_pubsub_proxy))
            tg.create_task(asyncio.to_thread(self._handle_create_push_socket_requests))
            tg.create_task(self._poll_push_sockets())

    def _run_pubsub_proxy(self) -> None:
        """Runs the ZMQ proxy for pubsub connections."""
        zmq.proxy(self._xsub_socket, self._xpub_socket)

    def _create_proxy_sockets(self) -> None:
        """Creates PUSH, XSUB, XPUB, and REP sockets for proxy."""
        # Create a PUSH socket to send messages to the main process
        self._push_socket = _create_sync_socket(zmq.PUSH, [(zmq.SNDHWM, 1)])
        self._push_socket.connect(self._pull_socket_address)

        # Create XSUB and XPUB sockets for the pubsub proxy
        self._xsub_socket = _create_sync_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)])
        self._xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")

        self._xpub_socket = _create_sync_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)])
        self._xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")

        # Create a REP socket to receive PUSH socket creation requests
        self._socket_rep_socket = _create_sync_socket(zmq.REP, [])
        self._socket_rep_port = self._socket_rep_socket.bind_to_random_port("tcp://*")

    def _handle_create_push_socket_requests(self) -> None:
        """Handles requests to create sockets in the subprocess."""
        while True:
            request_data = self._socket_rep_socket.recv_json()
            try:
                request = _PushSocketRequest.model_validate(request_data)
            except ValidationError:
                self._socket_rep_socket.send_json({"error": "Invalid request format."})
                continue
            try:
                push_address = self._create_push_socket(
                    request.topic, request.maxsize, reuse=request.reuse
                )
                self._socket_rep_socket.send_json({"push_address": push_address})
            except Exception as e:
                self._socket_rep_socket.send_json({"error": str(e)})

    def _create_push_socket(self, topic: str, maxsize: int, reuse: bool = True) -> str:
        """Creates a push socket in the subprocess and returns its address."""
        # Create the SUB socket to receive messages from the XPUB socket
        if reuse is False:
            raise NotImplementedError("PUSH socket reuse is not implemented yet.")
        if topic in self._push_sockets and reuse is True:
            push_address, _ = self._push_sockets[topic]
            return push_address
        sub_socket = create_socket(
            zmq.SUB, [(zmq.RCVHWM, self._maxsize), (zmq.SUBSCRIBE, topic.encode("utf8"))]
        )
        sub_socket.connect(f"{self._zmq_address}:{self._xpub_port}")
        self._push_poller.register(sub_socket, zmq.POLLIN)

        # Create the PUSH socket that clients will connect to
        push_socket = create_socket(zmq.PUSH, [(zmq.SNDHWM, maxsize)])
        push_port = push_socket.bind_to_random_port("tcp://*")
        push_address = f"{self._zmq_address}:{push_port}"
        self._push_sockets[topic] = (push_address, push_socket)

        return push_address

    async def _poll_push_sockets(self) -> None:
        """Polls push sockets for messages and sends them to the proxy."""
        while True:
            # Set a timeout of 1 second to allow for new push sockets to be added
            events = dict(await self._push_poller.poll(timeout=1000))
            async with asyncio.TaskGroup() as tg:
                for socket in events:
                    tg.create_task(self._handle_push_socket(socket))

    async def _handle_push_socket(self, socket: zmq.asyncio.Socket) -> None:
        msg = await socket.recv_multipart()
        topic = msg[0].decode("utf8")
        _, push_socket = self._push_sockets[topic]
        await push_socket.send_multipart(msg)

    def _close(self) -> None:  # pragma: no cover
        self._xsub_socket.close(linger=0)
        self._xpub_socket.close(linger=0)
        self._push_socket.close(linger=0)
        self._socket_rep_socket.close(linger=0)

    def terminate(self, timeout: _t.Optional[float] = None) -> None:
        """Terminate the child process and wait for it to exit."""
        if self._process is not None and self._process.is_alive():
            # Try SIGTERM first
            self._process.terminate()
            self._process.join(timeout=timeout)

            # If still alive, force SIGKILL
            if self._process.is_alive():  # pragma: no cover
                self._process.kill()
                self._process.join(timeout=1.0)  # Short timeout after SIGKILL

            self._process = None  # Abandon reference rather than raising an exception
