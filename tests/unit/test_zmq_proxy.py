"""Tests for ZMQProxy class."""

import asyncio
import typing as _t

import pytest
import zmq
import zmq.asyncio

from plugboard._zmq.zmq_proxy import ZMQ_ADDR, ZMQProxy, create_socket


@pytest.fixture
async def zmq_proxy() -> _t.AsyncGenerator[ZMQProxy, None]:
    """Fixture for ZMQProxy instance."""
    proxy = ZMQProxy()
    await proxy.start_proxy()

    try:
        yield proxy
    finally:
        proxy.terminate()
        await asyncio.sleep(0.1)  # Give the process time to terminate


@pytest.mark.anyio
async def test_start_proxy() -> None:
    """Tests that the ZMQProxy can be started."""
    proxy = ZMQProxy()
    try:
        # Start the proxy
        await proxy.start_proxy()
        assert proxy._proxy_started is True

        # Test that starting it again doesn't raise an error
        await proxy.start_proxy()

        # Test that starting with a different address raises an error
        with pytest.raises(RuntimeError, match="ZMQ proxy already started with different address"):
            await proxy.start_proxy(zmq_address="tcp://localhost")
    finally:
        proxy.terminate()
        await asyncio.sleep(0.1)


@pytest.mark.anyio
async def test_get_proxy_ports(zmq_proxy: ZMQProxy) -> None:
    """Tests retrieving proxy ports and verifies PUB/SUB connectivity."""
    # Test that ports are returned as integers
    xsub_port, xpub_port = await zmq_proxy.get_proxy_ports()
    assert isinstance(xsub_port, int)
    assert isinstance(xpub_port, int)
    assert xsub_port > 0
    assert xpub_port > 0

    # Test that the ports are cached
    xsub_port2, xpub_port2 = await zmq_proxy.get_proxy_ports()
    assert xsub_port == xsub_port2
    assert xpub_port == xpub_port2

    # Allow time for connections to be established
    await asyncio.sleep(0.1)

    # Test that PUB and SUB sockets can connect and exchange messages
    # Create a PUB socket to connect to xsub port
    pub_socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(f"{ZMQ_ADDR}:{xsub_port}")

    # Create a SUB socket to connect to xpub port
    topic = b"test_topic"
    sub_socket = create_socket(zmq.SUB, [(zmq.RCVHWM, 100), (zmq.SUBSCRIBE, topic)])
    sub_socket.connect(f"{ZMQ_ADDR}:{xpub_port}")

    # Allow time for connections to be established
    await asyncio.sleep(0.1)

    # Send a test message
    test_message = b"Hello ZMQ"
    await pub_socket.send_multipart([topic, test_message])

    # Receive the message with timeout
    received = await asyncio.wait_for(sub_socket.recv_multipart(), timeout=1.0)

    # Verify the message was received correctly
    assert len(received) == 2
    assert received[0] == topic
    assert received[1] == test_message

    # Clean up
    pub_socket.close()
    sub_socket.close()


@pytest.mark.anyio
async def test_get_proxy_ports_not_started() -> None:
    """Tests retrieving proxy ports when proxy is not started."""
    proxy = ZMQProxy()
    with pytest.raises(RuntimeError, match="ZMQ proxy not started"):
        await proxy.get_proxy_ports()


@pytest.mark.anyio
async def test_add_push_socket(zmq_proxy: ZMQProxy) -> None:
    """Tests adding a push socket for a topic."""
    topic: str = "test_topic"

    # Get the ports first to ensure the proxy is initialized
    await zmq_proxy.get_proxy_ports()

    # Test creating a push socket
    push_addr: str = await zmq_proxy.add_push_socket(topic)
    assert isinstance(push_addr, str)
    assert push_addr.startswith(ZMQ_ADDR)

    # Create a subscriber to send a message through the proxy
    xsub_port, _ = await zmq_proxy.get_proxy_ports()

    # Create a publisher socket
    pub_socket: zmq.asyncio.Socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(f"{ZMQ_ADDR}:{xsub_port}")

    # Create a pull socket to receive the message
    pull_socket_1: zmq.asyncio.Socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 100)])
    pull_socket_1.connect(push_addr)

    # Create a second pull socket to check message can only be received once
    pull_socket_2: zmq.asyncio.Socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 100)])
    pull_socket_2.connect(push_addr)

    # Allow the connections to be established
    await asyncio.sleep(0.1)

    # Send a message
    message: bytes = b"test message"
    topic_bytes: bytes = topic.encode("utf8")
    await pub_socket.send_multipart([topic_bytes, message])

    # Wait for the message to be proxied
    await asyncio.sleep(0.1)

    # Check that the message was received
    received: list[bytes] = await asyncio.wait_for(pull_socket_1.recv_multipart(), timeout=1.0)
    assert received == [topic_bytes, message]

    # Check that attempting to receive the same message with second socket fails
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(pull_socket_2.recv_multipart(), timeout=1.0)

    # Clean up
    pub_socket.close()
    pull_socket_1.close()
    pull_socket_2.close()


@pytest.mark.anyio
async def test_add_push_socket_not_started() -> None:
    """Tests adding a push socket when proxy is not started."""
    proxy = ZMQProxy()
    with pytest.raises(RuntimeError, match="ZMQ proxy .* not set"):
        await proxy.add_push_socket("test_topic")


@pytest.mark.anyio
async def test_add_multiple_push_sockets(zmq_proxy: ZMQProxy) -> None:
    """Tests adding multiple push sockets for different topics."""
    # Get the ports first to ensure the proxy is initialized
    await zmq_proxy.get_proxy_ports()

    # Create multiple push sockets for different topics
    topic1: str = "test_topic_1"
    topic2: str = "test_topic_2"

    push_addr1: str = await zmq_proxy.add_push_socket(topic1)
    push_addr2: str = await zmq_proxy.add_push_socket(topic2)

    # Verify they're different addresses
    assert push_addr1 != push_addr2

    # Test that both sockets work correctly
    xsub_port, _ = await zmq_proxy.get_proxy_ports()

    # Create a publisher socket
    pub_socket: zmq.asyncio.Socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(f"{ZMQ_ADDR}:{xsub_port}")

    # Create pull sockets
    pull_socket1: zmq.asyncio.Socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 100)])
    pull_socket1.connect(push_addr1)

    pull_socket2: zmq.asyncio.Socket = create_socket(zmq.PULL, [(zmq.RCVHWM, 100)])
    pull_socket2.connect(push_addr2)

    # Allow the connections to be established
    await asyncio.sleep(0.1)

    # Send messages to both topics
    await pub_socket.send_multipart([topic1.encode(), b"message 1"])
    await pub_socket.send_multipart([topic2.encode(), b"message 2"])

    # Wait for the messages to be proxied
    await asyncio.sleep(0.1)

    # Check that the messages were received by the right sockets
    received1: list[bytes] = await asyncio.wait_for(pull_socket1.recv_multipart(), timeout=1.0)
    assert received1[1] == b"message 1"

    received2: list[bytes] = await asyncio.wait_for(pull_socket2.recv_multipart(), timeout=1.0)
    assert received2[1] == b"message 2"

    # Clean up
    pub_socket.close()
    pull_socket1.close()
    pull_socket2.close()
