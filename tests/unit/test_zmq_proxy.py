"""Tests for ZMQProxy class."""

import asyncio
import typing as _t

import pytest
import pytest_asyncio
import zmq
import zmq.asyncio

from plugboard._zmq.zmq_proxy import ZMQ_ADDR, ZMQProxy, create_socket, zmq_sockopts_t


@pytest_asyncio.fixture
async def zmq_proxy() -> _t.AsyncGenerator[ZMQProxy, None]:
    """Fixture for ZMQProxy instance."""
    proxy = ZMQProxy()
    # No need to explicitly start_proxy as it's done in __init__

    try:
        yield proxy
    finally:
        proxy.terminate()
        await asyncio.sleep(0.1)  # Give the process time to terminate


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "socket_pair,socket_opts,topic",
    [
        # PUSH-PULL pair
        (
            (zmq.PUSH, zmq.PULL),
            ([(zmq.SNDHWM, 100)], [(zmq.RCVHWM, 100)]),
            None,
        ),
        # PUB-SUB pair with topic
        (
            (zmq.PUB, zmq.SUB),
            ([(zmq.SNDHWM, 100)], [(zmq.RCVHWM, 100), (zmq.SUBSCRIBE, b"test")]),
            b"test",
        ),
        # DEALER-ROUTER pair
        (
            (zmq.DEALER, zmq.ROUTER),
            ([(zmq.SNDHWM, 100)], [(zmq.RCVHWM, 100)]),
            None,
        ),
        # REQ-REP pair
        (
            (zmq.REQ, zmq.REP),
            ([(zmq.SNDHWM, 100)], [(zmq.RCVHWM, 100)]),
            None,
        ),
    ],
)
async def test_create_socket(
    socket_pair: tuple[int, int],
    socket_opts: tuple[zmq_sockopts_t, zmq_sockopts_t],
    topic: _t.Optional[bytes],
) -> None:
    """Tests that the create_socket function creates properly connected sockets."""
    sender_type, receiver_type = socket_pair
    sender_opts, receiver_opts = socket_opts

    # Create the sockets
    sender = create_socket(sender_type, sender_opts)
    port = sender.bind_to_random_port("tcp://*")

    receiver = create_socket(receiver_type, receiver_opts)
    receiver.connect(f"tcp://127.0.0.1:{port}")

    # Allow time for connections to be established
    await asyncio.sleep(0.1)

    # Prepare test message
    test_message = b"Test message"

    if sender_type == zmq.PUB and receiver_type == zmq.SUB:
        # For PUB-SUB, prepend topic
        assert topic is not None
        to_send = [topic, test_message]
    elif sender_type == zmq.REQ and receiver_type == zmq.REP:
        # For REQ-REP, we need to send then receive then send back
        to_send = [test_message]
        await sender.send_multipart(to_send)
        received = await asyncio.wait_for(receiver.recv_multipart(), timeout=1.0)
        assert received == to_send
        await receiver.send_multipart([b"Reply"])
        reply = await asyncio.wait_for(sender.recv_multipart(), timeout=1.0)
        assert reply == [b"Reply"]
        sender.close()
        receiver.close()
        return
    else:
        to_send = [test_message]

    # Send the message
    await sender.send_multipart(to_send)

    # Receive and verify
    received = await asyncio.wait_for(receiver.recv_multipart(), timeout=1.0)

    if sender_type == zmq.DEALER and receiver_type == zmq.ROUTER:
        # ROUTER prepends sender identity to the message
        assert len(received) > len(to_send)
        assert received[-1] == test_message
    else:
        assert len(received) == len(to_send)
        if sender_type == zmq.PUB:
            assert received[0] == topic
            assert received[1] == test_message
        else:
            assert received[0] == test_message

    # Clean up
    sender.close()
    receiver.close()


@pytest.mark.asyncio
async def test_start_proxy() -> None:
    """Tests that the ZMQProxy can be started."""
    # Creating ZMQProxy automatically starts it
    proxy = ZMQProxy()
    try:
        # Verify the proxy is started by checking a property that requires a started proxy
        assert proxy._proxy_started is True

        # Test that calling _start_proxy again doesn't raise an error
        proxy._start_proxy()

        # Test that calling _start_proxy with a different address raises an error
        with pytest.raises(RuntimeError, match="ZMQ proxy already started with different address"):
            proxy._start_proxy(zmq_address="tcp://localhost")
    finally:
        proxy.terminate()
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_get_proxy_ports(zmq_proxy: ZMQProxy) -> None:
    """Tests retrieving proxy ports and verifies PUB/SUB connectivity."""
    # Test that ports are returned as integers
    # Using xsub_addr and xpub_addr properties instead of get_proxy_ports method
    xsub_addr = zmq_proxy.xsub_addr
    xpub_addr = zmq_proxy.xpub_addr

    # Extract ports from addresses
    xsub_port = int(xsub_addr.split(":")[-1])
    xpub_port = int(xpub_addr.split(":")[-1])

    assert isinstance(xsub_port, int)
    assert isinstance(xpub_port, int)
    assert xsub_port > 0
    assert xpub_port > 0

    # Test that the address properties return consistent values
    assert zmq_proxy.xsub_addr == xsub_addr
    assert zmq_proxy.xpub_addr == xpub_addr

    # Allow time for connections to be established
    await asyncio.sleep(0.1)

    # Test that PUB and SUB sockets can connect and exchange messages
    # Create a PUB socket to connect to xsub port
    pub_socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(xsub_addr)

    # Create a SUB socket to connect to xpub port
    topic = b"test_topic"
    sub_socket = create_socket(zmq.SUB, [(zmq.RCVHWM, 100), (zmq.SUBSCRIBE, topic)])
    sub_socket.connect(xpub_addr)

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


@pytest.mark.asyncio
async def test_get_proxy_ports_not_started() -> None:
    """Tests retrieving proxy ports when proxy is not started."""
    # Create a proxy but interfere with its initialization
    proxy = ZMQProxy()
    proxy._proxy_started = False  # Force the proxy to appear not started

    with pytest.raises(RuntimeError, match="ZMQ .* not set"):
        # Try to access properties that require a started proxy
        _ = proxy.xsub_addr

    with pytest.raises(RuntimeError, match="ZMQ .* not set"):
        _ = proxy.xpub_addr

    # Clean up
    proxy.terminate()


@pytest.mark.flaky(reruns=3)
@pytest.mark.asyncio
async def test_add_push_socket(zmq_proxy: ZMQProxy) -> None:
    """Tests adding a push socket for a topic."""
    topic: str = "test_topic"

    # Test creating a push socket
    push_addr: str = await zmq_proxy.add_push_socket(topic)
    assert isinstance(push_addr, str)
    assert push_addr.startswith(ZMQ_ADDR)

    # Create a subscriber to send a message through the proxy
    pub_socket: zmq.asyncio.Socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(zmq_proxy.xsub_addr)

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


@pytest.mark.asyncio
async def test_add_push_socket_not_started() -> None:
    """Tests adding a push socket when proxy is not started."""
    proxy = ZMQProxy()
    proxy._proxy_started = False  # Force the proxy to appear not started

    with pytest.raises(RuntimeError, match="ZMQ proxy .* not set"):
        await proxy.add_push_socket("test_topic")

    # Clean up
    proxy.terminate()


@pytest.mark.asyncio
async def test_add_push_socket_invalid_request(zmq_proxy: ZMQProxy) -> None:
    """Tests adding a push socket with invalid request data raises `ValidationError`."""
    # Create a topic with invalid characters

    # Attempt to add the push socket and expect a ValidationError
    with pytest.raises(RuntimeError, match="Failed to create push socket.*"):
        await zmq_proxy.add_push_socket(topic="_")

    with pytest.raises(RuntimeError, match="Failed to create push socket.*"):
        await zmq_proxy.add_push_socket(topic="valid_topic", maxsize=0)

    # Clean up
    zmq_proxy.terminate()
    await asyncio.sleep(0.1)


@pytest.mark.flaky(reruns=3)
@pytest.mark.asyncio
async def test_add_multiple_push_sockets(zmq_proxy: ZMQProxy) -> None:
    """Tests adding multiple push sockets for different topics."""
    # Create multiple push sockets for different topics
    topic1: str = "test_topic_1"
    topic2: str = "test_topic_2"

    push_addr1: str = await zmq_proxy.add_push_socket(topic1)
    push_addr2: str = await zmq_proxy.add_push_socket(topic2)

    # Verify they're different addresses
    assert push_addr1 != push_addr2

    # Test that both sockets work correctly
    # Create a publisher socket
    pub_socket: zmq.asyncio.Socket = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
    pub_socket.connect(zmq_proxy.xsub_addr)

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
