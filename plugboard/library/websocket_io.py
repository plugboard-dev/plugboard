"""Provides `WebsocketReader` and `WebsocketWriter` realtime data in Plugboard."""

from contextlib import AsyncExitStack
import typing as _t

import msgspec.json as json

from plugboard.component import Component, IOController
from plugboard.utils import depends_on_optional


try:
    from websockets.asyncio.client import connect
    from websockets.asyncio.connection import Connection
    from websockets.exceptions import ConnectionClosed
except ImportError:
    pass


class WebsocketReader(Component):
    """Reads data from a websocket connection."""

    io = IOController(outputs=["message"])

    @depends_on_optional("websockets")
    def __init__(
        self,
        name: str,
        uri: str,
        connect_args: dict[str, _t.Any] | None = None,
        initial_message: _t.Any | None = None,
        parse_json: bool = False,
        *args: _t.Any,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates the `WebsocketReader`.

        See https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html for possible
        connection arguments that can be passed using `connect_args`. This `WebsocketReader` will
        run until interrupted, and automatically reconnect if the server connection is lost.

        Args:
            name: The name of the `WebsocketReader`.
            uri: The URI of the WebSocket server.
            connect_args: Optional; Additional arguments to pass to the WebSocket connection.
            initial_message: Optional; The initial message to send to the WebSocket server on
                connection. Can be used to subscribe to a specific topic.
            parse_json: Whether to parse the received data as JSON.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(name, *args, **kwargs)
        self._uri = uri
        self._connect_args = connect_args if connect_args else {}
        if initial_message is not None:
            self._initial_message = json.encode(initial_message) if parse_json else initial_message
        else:
            self._initial_message = None
        self._parse_json = parse_json
        self._ctx = AsyncExitStack()
        self._conn: Connection | None = None

    async def init(self) -> None:
        """Initializes the websocket connection."""
        self._conn_iter = aiter(connect(self._uri, **self._connect_args))
        self._conn = await self._get_conn()
        self._logger.info(f"Connected to {self._uri}")

    async def _get_conn(self) -> Connection:
        conn = await self._ctx.enter_async_context(await anext(self._conn_iter))
        if self._initial_message is not None:
            self._logger.info(f"Sending initial message", message=self._initial_message)
            await conn.send(self._initial_message)
        return conn

    async def step(self) -> None:
        """Reads a message from the websocket connection."""
        if not self._conn:
            self._conn = await self._get_conn()
        try:
            message = await self._conn.recv()
            self.message = json.decode(message) if self._parse_json else message
        except ConnectionClosed:
            self._logger.warning(f"Connection to {self._uri} closed, will reconnect...")
            self._conn = None

    async def destroy(self) -> None:
        """Closes the websocket connection."""
        await self._ctx.aclose()


class WebsocketWriter(Component):
    """Writes data to a websocket connection."""

    io = IOController(inputs=["message"])

    @depends_on_optional("websockets")
    def __init__(
        self,
        name: str,
        uri: str,
        connect_args: dict[str, _t.Any] | None = None,
        parse_json: bool = False,
        *args: _t.Any,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates the `WebsocketWriter`.

        See https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html for possible
        connection arguments that can be passed using `connect_args`.

        Args:
            name: The name of the `WebsocketWriter`.
            uri: The URI of the WebSocket server.
            connect_args: Optional; Additional arguments to pass to the websocket connection.
            parse_json: Whether to convert the data to JSON before sending.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(name, *args, **kwargs)
        self._uri = uri
        self._connect_args = connect_args if connect_args else {}
        self._parse_json = parse_json
        self._ctx = AsyncExitStack()

    async def init(self) -> None:
        """Initializes the websocket connection."""
        self._conn_iter = aiter(connect(self._uri, **self._connect_args))
        self._conn = await self._get_conn()
        self._logger.info(f"Connected to {self._uri}")

    async def _get_conn(self) -> Connection:
        return await self._ctx.enter_async_context(await anext(self._conn_iter))

    async def step(self) -> None:
        """Writes a message to the websocket connection."""
        message = json.encode(self.message) if self._parse_json else self.message
        while True:
            try:
                await self._conn.send(message)
                break
            except ConnectionClosed:
                self._logger.warning(f"Connection to {self._uri} closed, will reconnect...")
                await self._ctx.aclose()
                self._conn = await self._get_conn()

    async def destroy(self) -> None:
        """Closes the websocket connection."""
        await self._ctx.aclose()
