"""Unit tests for the websocket components."""

import json
import typing as _t

import pytest
import pytest_asyncio
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import ServerConnection, serve

from plugboard.library.websocket_io import WebsocketBase, WebsocketReader, WebsocketWriter


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


@pytest_asyncio.fixture
async def connected_client() -> _t.AsyncGenerator[ClientConnection, None]:
    """Returns a client to a websocket broadcast server."""
    async with serve(_handler, HOST, PORT):
        async with connect(f"ws://{HOST}:{PORT}") as client:
            yield client


@pytest.mark.flaky(reruns=3)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parse_json,initial_message,n_skip_messages",
    [
        (True, None, 0),
        (False, None, 1),
        (True, {"msg": "hello!"}, 0),
        (True, {"msg": "hello!"}, 3),
        (False, "G'day!", 0),
    ],
)
async def test_websocket_reader(
    connected_client: ClientConnection,
    parse_json: bool,
    initial_message: _t.Any,
    n_skip_messages: int,
) -> None:
    """Tests the `WebsocketReader`."""
    reader = WebsocketReader(
        name="test-websocket",
        uri=f"ws://{HOST}:{PORT}",
        skip_messages=n_skip_messages,
        parse_json=parse_json,
        initial_message=initial_message,
    )
    await reader.init()
    # Send some messages to the server for broadcast to the reader
    messages = [{"test-msg": x} for x in range(5)]
    for message in messages:
        await connected_client.send(json.dumps(message))

    # Prepare the expected messages: intitial message + messages
    expected_messages = [json.dumps(message) if not parse_json else message for message in messages]
    expected_messages = (
        [initial_message] + expected_messages if initial_message is not None else expected_messages
    )
    expected_messages = expected_messages[n_skip_messages:]
    # Check that the reader receives the messages, correctly parsed
    for received_message in expected_messages:
        await reader.step()
        assert received_message == reader.message

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
        writer.message = message if parse_json else json.dumps(message)  # type: ignore [attr-defined]
        await writer.step()
        # Now retrieve the message from the broadcast
        response = await connected_client.recv()
        assert message == json.loads(response) if parse_json else response

    await writer.destroy()


@pytest.mark.asyncio
@pytest.mark.parametrize("component", [WebsocketReader, WebsocketWriter])
async def test_websocket_error(component: _t.Type[WebsocketBase]) -> None:
    """Tests the error handling of the websocket components."""
    c = component(
        name="test-websocket", uri=f"ws://{HOST}:{PORT}", connect_args={"open_timeout": 0.01}
    )
    with pytest.raises(OSError):
        await c.init()
