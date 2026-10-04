"""Tests for ZMQChannel backend-specific behavior."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from plugboard._zmq.backend import ZMQ_BACKEND_PYOMQ
from plugboard.connector.zmq_channel import PYOMQ_CLOSE_DRAIN_SECONDS, ZMQChannel


@pytest.mark.asyncio
async def test_close_drains_pyomq_send_socket() -> None:
    """PyOMQ channels allow queued close frames to reach the proxy before closing."""
    send_socket = Mock()
    send_socket.send_multipart = AsyncMock()
    channel = ZMQChannel(send_socket=send_socket)

    with patch("plugboard.connector.zmq_channel.zmq_backend", ZMQ_BACKEND_PYOMQ):
        with patch(
            "plugboard.connector.zmq_channel.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            await channel.close()

    sleep.assert_awaited_once_with(PYOMQ_CLOSE_DRAIN_SECONDS)
    send_socket.close.assert_called_once_with()
    assert channel.is_closed
