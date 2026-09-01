"""Tests for ZMQ backend selection."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap

import pytest

from plugboard._zmq.backend import ZMQ_BACKEND_ENV


def _run_backend_probe(
    code: str,
    backend: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if backend is not None:
        env[ZMQ_BACKEND_ENV] = backend
    if extra_env is not None:
        env.update(extra_env)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(code)],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def test_default_zmq_backend_is_pyzmq() -> None:
    """The default ZMQ backend remains PyZMQ."""
    result = _run_backend_probe(
        """
        from plugboard._zmq.backend import zmq_backend, zmq
        print(zmq_backend)
        print(zmq.__name__)
        """,
        extra_env={ZMQ_BACKEND_ENV: ""},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["pyzmq", "zmq"]


def test_invalid_zmq_backend_fails_with_clear_error() -> None:
    """Unsupported backend names fail during import with a clear error."""
    result = _run_backend_probe(
        """
        import plugboard._zmq.backend
        """,
        backend="not-a-backend",
    )

    assert result.returncode != 0
    assert "Unsupported ZMQ backend" in result.stderr
    assert ZMQ_BACKEND_ENV in result.stderr


@pytest.mark.skipif(importlib.util.find_spec("pyomq") is None, reason="pyomq not installed")
def test_pyomq_backend_supports_create_socket() -> None:
    """The pyomq backend can run the ZMQ socket helper."""
    result = _run_backend_probe(
        """
        import asyncio

        from plugboard._zmq.backend import zmq, zmq_backend
        from plugboard._zmq.zmq_proxy import create_socket

        async def main() -> None:
            pull = create_socket(zmq.PULL, [(zmq.RCVHWM, 100)])
            port = pull.bind_to_random_port("tcp://127.0.0.1")
            push = create_socket(zmq.PUSH, [(zmq.SNDHWM, 100)])
            push.connect(f"tcp://127.0.0.1:{port}")
            await asyncio.sleep(0.2)
            await push.send_multipart([b"", b"payload"])
            got = await asyncio.wait_for(pull.recv_multipart(), timeout=1.0)
            assert got == [b"", b"payload"]
            push.close(linger=0)
            pull.close(linger=0)
            print(zmq_backend)

        asyncio.run(main())
        """,
        backend="pyomq",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pyomq"


@pytest.mark.skipif(importlib.util.find_spec("pyomq") is None, reason="pyomq not installed")
def test_pyomq_backend_supports_zmq_proxy() -> None:
    """The pyomq backend can run the ZMQ proxy process."""
    result = _run_backend_probe(
        """
        import asyncio

        from plugboard._zmq.backend import zmq
        from plugboard._zmq.zmq_proxy import ZMQProxy, create_socket

        async def main() -> None:
            proxy = ZMQProxy(maxsize=100)
            try:
                topic = b"topic"
                sub = create_socket(
                    zmq.SUB,
                    [(zmq.RCVHWM, 100), (zmq.SUBSCRIBE, topic)],
                )
                sub.connect(proxy.xpub_addr)
                pub = create_socket(zmq.PUB, [(zmq.SNDHWM, 100)])
                pub.connect(proxy.xsub_addr)
                await asyncio.sleep(0.3)
                await pub.send_multipart([topic, b"payload"])
                got = await asyncio.wait_for(sub.recv_multipart(), timeout=1.0)
                assert got == [topic, b"payload"]
                pub.close(linger=0)
                sub.close(linger=0)
            finally:
                proxy.terminate(timeout=5.0)

        asyncio.run(main())
        """,
        backend="pyomq",
    )

    assert result.returncode == 0, result.stderr
