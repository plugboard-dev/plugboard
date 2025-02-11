"""Unit tests for the websocket components."""

import typing as _t

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import serve

from plugboard.library.websocket_io import WebsocketReader


HOST = "localhost"
PORT = 8767
CLIENTS = set()


async def _handler(websocket):
    """Broadcasts messages to all connected clients."""
    CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.remove(websocket)


@pytest.fixture
async def connected_client() -> _t.AsyncIterable[ClientConnection]:
    """Returns a client to a websocket broadcast server."""
    async with serve(_handler, HOST, PORT):
        client = await connect(f"ws://{HOST}:{PORT}")
        yield client


@pytest.mark.asyncio
async def test_websocket_reader(connected_client: ClientConnection) -> None:
    """Tests the `WebsocketReader`."""
    reader = WebsocketReader(name="test-websocket", uri=f"ws://{HOST}:{PORT}")
    await reader.init()
    messages = [str(x) for x in range(5)]
    for message in messages:
        await connected_client.send(message)

    # Check that the reader receives the messages
    for message in messages:
        await reader.step()
        assert reader.message == message
