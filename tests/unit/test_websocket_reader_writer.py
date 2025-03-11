"""Unit tests for the websocket components."""

import json
import typing as _t

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import ServerConnection, serve

from plugboard.library.websocket_io import WebsocketReader, WebsocketWriter


HOST = "localhost"
PORT = 8767
CLIENTS: set[ServerConnection] = set()


async def _handler(websocket: ServerConnection) -> None:
    """Broadcasts incoming messages to all connected clients."""
    CLIENTS.add(websocket)
    try:
        async for message in websocket:
            for client in CLIENTS:
                await client.send(message)
    finally:
        CLIENTS.remove(websocket)


@pytest.fixture
async def connected_client() -> _t.AsyncIterable[ClientConnection]:
    """Returns a client to a websocket broadcast server."""
    async with serve(_handler, HOST, PORT):
        async with connect(f"ws://{HOST}:{PORT}") as client:
            yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parse_json,initial_message",
    [(True, None), (False, None), (True, {"msg": "hello!"}), (False, "G'day!")],
)
async def test_websocket_reader(
    connected_client: ClientConnection, parse_json: bool, initial_message: _t.Any
) -> None:
    """Tests the `WebsocketReader`."""
    reader = WebsocketReader(
        name="test-websocket",
        uri=f"ws://{HOST}:{PORT}",
        parse_json=parse_json,
        initial_message=initial_message,
    )
    await reader.init()
    # Send some messages to the server for broadcast to the reader
    messages = [{"test-msg": x} for x in range(5)]
    for message in messages:
        await connected_client.send(json.dumps(message))

    # If initial message set, it should be received first
    if initial_message is not None:
        await reader.step()
        assert initial_message == reader.message
    # Check that the reader receives the messages, correctly parsed
    for message in messages:
        await reader.step()
        assert message == reader.message if parse_json else json.loads(reader.message)

    await reader.destroy()


@pytest.mark.asyncio
@pytest.mark.parametrize("parse_json", [True, False])
async def test_websocket_writer(connected_client: ClientConnection, parse_json: bool) -> None:
    """Tests the `WebsocketWriter`."""
    writer = WebsocketWriter(
        name="test-websocket",
        uri=f"ws://{HOST}:{PORT}",
        parse_json=parse_json,
    )
    await writer.init()
    messages = [{"test-msg": x} for x in range(5)]
    for message in messages:
        writer.message = message if parse_json else json.dumps(message)
        await writer.step()
        # Now retrieve the message from the broadcast
        response = await connected_client.recv()
        assert message == json.loads(response) if parse_json else response

    await writer.destroy()
