"""Provides `WebsocketReader` and `WebsocketWriter` realtime data in Plugboard."""

from __future__ import annotations

from abc import ABC
from contextlib import AsyncExitStack
import typing as _t

import msgspec.json as json

from plugboard.component import Component, IOController
from plugboard.schemas import ComponentArgsDict
from plugboard.utils import depends_on_optional


try:
    from websockets.asyncio.client import connect, process_exception
    from websockets.exceptions import ConnectionClosed
    from websockets.typing import Data
except ImportError:
    pass

if _t.TYPE_CHECKING:  # pragma: no cover
    from websockets.asyncio.connection import Connection


class WebsocketArgsDict(ComponentArgsDict):
    """Specification of the `WebsocketBase` constructor arguments."""

    uri: str
    connect_args: _t.NotRequired[dict[str, _t.Any] | None]


class WebsocketBase(Component, ABC):
    """Base [`Component`][plugboard.component.Component] for websocket connections.

    See [websockets](https://websockets.readthedocs.io/en/stable/index.html) for more info on the
    underlying websocket library.
    """

    io = IOController()

    @depends_on_optional("websockets")
    def __init__(
        self,
        uri: str,
        connect_args: dict[str, _t.Any] | None = None,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiates the [`Component`][plugboard.component.Component].

        Args:
            uri: The URI of the WebSocket server.
            connect_args: Optional; Additional arguments to pass to the WebSocket connection.
            **kwargs: Additional keyword arguments for [`Component`][plugboard.component.Component].
        """
        super().__init__(**kwargs)
        self._uri = uri
        self._connect_args = {"process_exception": self._process_exception, **(connect_args or {})}
        self._connection_success = False
        self._ctx = AsyncExitStack()

    def _process_exception(self, exc: Exception) -> Exception | None:
        if not self._connection_success:
            self._logger.error("Error connecting to websocket", exc_info=exc)
            return exc
        # If connection was established, use the default exception handler
        self._logger.info("Error raised in websocket connection", exc_info=exc)
        return process_exception(exc)

    async def init(self) -> None:
        """Initializes the websocket connection."""
        self._conn_iter = aiter(connect(self._uri, **self._connect_args))
        self._conn = await self._get_conn()
        self._connection_success = True
        self._logger.info(f"Connected to {self._uri}")

    async def _get_conn(self) -> Connection:
        conn = await self._ctx.enter_async_context(await anext(self._conn_iter))
        return conn

    async def destroy(self) -> None:
        """Closes the websocket connection."""
        await self._ctx.aclose()


class WebsocketReader(WebsocketBase):
    """Reads data from a websocket connection."""

    io = IOController(outputs=["message"])

    def __init__(
        self,
        initial_message: _t.Any | None = None,
        skip_messages: int = 0,
        parse_json: bool = False,
        **kwargs: _t.Unpack[WebsocketArgsDict],
    ) -> None:
        """Instantiates the `WebsocketReader`.

        See [here](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html) for
        possible connection arguments that can be passed using `connect_args`. This
        `WebsocketReader` will run until interrupted, and automatically reconnect if the server
        connection is lost.

        Args:
            initial_message: Optional; The initial message to send to the WebSocket server on
                connection. Can be used to subscribe to a specific topic.
            skip_messages: The number of messages to ignore before starting to read messages.
            parse_json: Whether to parse the received data as JSON.
            **kwargs: Additional keyword arguments for
                [`WebsocketBase`][plugboard.library.websocket_io.WebsocketBase].
        """
        super().__init__(**kwargs)
        if initial_message is not None:
            self._initial_message = json.encode(initial_message) if parse_json else initial_message
        else:
            self._initial_message = None
        self._skip_messages = skip_messages
        self._skip_count = 0
        self._parse_json = parse_json

    async def _get_conn(self) -> Connection:
        conn = await super()._get_conn()
        if self._initial_message is not None:
            self._logger.info(f"Sending initial message", message=self._initial_message)
            await conn.send(self._initial_message)
        self._skip_count = self._skip_messages
        return conn

    async def _recv_websocket(self) -> _t.Optional["Data"]:
        try:
            return await self._conn.recv()
        except ConnectionClosed:
            self._logger.warning(f"Connection to {self._uri} closed, will reconnect...")
            await self._ctx.aclose()
            self._conn = await self._get_conn()
        return None

    async def step(self) -> None:
        """Reads a message from the websocket connection."""
        while self._skip_count > 0:
            message = await self._recv_websocket()
            if message is None:
                continue
            self._logger.info(f"Skipping message", message=message)
            self._skip_count -= 1
        while True:
            message = await self._recv_websocket()
            if message is not None:
                break
        self.message = json.decode(message) if self._parse_json else message


class WebsocketWriter(WebsocketBase):
    """Writes data to a websocket connection."""

    io = IOController(inputs=["message"])

    def __init__(
        self,
        parse_json: bool = False,
        **kwargs: _t.Unpack[WebsocketArgsDict],
    ) -> None:
        """Instantiates the `WebsocketWriter`.

        See [here](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html) for
        possible connection arguments that can be passed using `connect_args`.

        Args:
            parse_json: Whether to convert the data to JSON before sending.
            **kwargs: Additional keyword arguments for
                [`WebsocketBase`][plugboard.library.websocket_io.WebsocketBase].
        """
        super().__init__(**kwargs)
        self._parse_json = parse_json

    async def _send_websocket(self, message: _t.Any) -> bool:
        try:
            await self._conn.send(message)
            return True
        except ConnectionClosed:
            self._logger.warning(f"Connection to {self._uri} closed, will reconnect...")
            await self._ctx.aclose()
            self._conn = await self._get_conn()
        return False

    async def step(self) -> None:
        """Writes a message to the websocket connection."""
        message = json.encode(self.message) if self._parse_json else self.message
        while True:
            success = await self._send_websocket(message)
            if success:
                break
