"""Provides `WebsocketReader` and `WebsocketWriter` realtime data in Plugboard."""

from contextlib import AsyncExitStack
import typing as _t

import msgspec.json as json
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from plugboard.component import Component, IOController


class WebsocketReader(Component):
    """Reads data from a WebSocket connection."""

    io = IOController(outputs=["message"])

    def __init__(
        self,
        name: str,
        uri: str,
        connect_args: dict[str, _t.Any] | None = None,
        initial_message: dict | str | None = None,
        parse_json: bool = False,
        *args: _t.Any,
        **kwargs: _t.Any,
    ) -> None:
        """Instantiates the `WebsocketReader`.

        See https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html for possible
        connection arguments that can be passed using `connect_args`.

        Args:
            name: The name of the `WebsocketReader`.
            uri: The URI of the WebSocket server.
            connect_args: Optional; Additional arguments to pass to the WebSocket connection.
            initial_message: Optional; The initial message to send to the WebSocket server.
            parse_json: Whether to parse the received data as JSON.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(name=name, *args, **kwargs)
        self._uri = uri
        self._connect_args = connect_args if connect_args else {}
        self._parse_json = parse_json
        self._ctx = AsyncExitStack()

    async def init(self) -> None:
        """Initializes the WebSocket connection."""
        self._conn = await self._ctx.enter_async_context(connect(self._uri, **self._connect_args))

    async def step(self) -> None:
        """Reads a message from the WebSocket connection."""
        # self.logger.info(f"Connected to {self._uri}")
        try:
            message = await self._conn.recv()
            if self._parse_json:
                message = json.decode(message)
            self.message = message
        except ConnectionClosed:
            # self.logger.warning(f"Connection to {self._uri} closed, reconnecting...")
            await self.io.close()

    async def destroy(self) -> None:
        """Closes the WebSocket connection."""
        await self._ctx.aclose()
