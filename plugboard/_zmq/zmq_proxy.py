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
        self._zmq_address = zmq_address
        self._zmq_proxy_lock = asyncio.Lock()
        self._maxsize = maxsize
        self._pull_socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 1)])
        self._pull_socket_port = self._pull_socket.bind_to_random_port("tcp://*")
        self._pull_socket_addr = f"{self._zmq_address}:{self._pull_socket_port}"
        self._xsub_port: _t.Optional[int] = None
        self._xpub_port: _t.Optional[int] = None
        self._proxy_started: bool = False

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        if "_pull_socket" in state:
            del state["_pull_socket"]
        if "_zmq_proxy_lock" in state:
            del state["_zmq_proxy_lock"]
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
            self._pull_socket_addr = f"{self._zmq_address}:{self._pull_socket_port}"
            self.start()
            self._proxy_started = True

    async def get_proxy_ports(self) -> tuple[int, int]:
        """Returns tuple of form (xsub port, xpub port) for the ZMQ proxy."""
        if not self._proxy_started:
            raise RuntimeError("ZMQ proxy not started.")
        async with self._zmq_proxy_lock:
            if self._xsub_port is None or self._xpub_port is None:
                ports_msg = await self._pull_socket.recv_multipart()
                self._xsub_port, self._xpub_port = map(int, ports_msg)
            return self._xsub_port, self._xpub_port

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

    def _run_pubsub_proxy(self) -> None:
        """Runs the ZMQ proxy for pubsub connections."""
        xsub_port, xpub_port = self._create_sockets()
        ports_msg = [str(xsub_port).encode(), str(xpub_port).encode()]
        self._push_socket.send_multipart(ports_msg)
        zmq.proxy(self._xsub_socket, self._xpub_socket)

    def _create_sockets(self) -> _t.Tuple[int, int]:
        """Creates XSUB, XPUB, and PUSH sockets for proxy and returns XSUB and XPUB ports."""
        ctx = zmq.Context.instance()
        self._xsub_socket = create_socket(zmq.XSUB, [(zmq.RCVHWM, self._maxsize)], ctx=ctx)
        xsub_port = self._xsub_socket.bind_to_random_port("tcp://*")

        self._xpub_socket = create_socket(zmq.XPUB, [(zmq.SNDHWM, self._maxsize)], ctx=ctx)
        xpub_port = self._xpub_socket.bind_to_random_port("tcp://*")

        self._push_socket = create_socket(zmq.PUSH, [(zmq.RCVHWM, 1)], ctx=ctx)
        self._push_socket.connect(self._pull_socket_addr)

        return xsub_port, xpub_port

    def _close(self) -> None:
        self._xsub_socket.close(linger=0)
        self._xpub_socket.close(linger=0)
        self._push_socket.close(linger=0)
