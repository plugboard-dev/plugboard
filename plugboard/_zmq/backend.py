"""Selects the ZeroMQ Python backend."""

from __future__ import annotations

import os
import typing as _t


ZMQ_BACKEND_ENV = "PLUGBOARD_ZMQ_BACKEND"
ZMQ_BACKEND_PYZMQ = "pyzmq"
ZMQ_BACKEND_PYOMQ = "pyomq"
ZMQ_BACKENDS = frozenset({ZMQ_BACKEND_PYZMQ, ZMQ_BACKEND_PYOMQ})


class ZMQBackendImportError(ImportError):
    """Raised when the selected ZeroMQ backend cannot be imported."""


def _backend_name() -> str:
    backend = os.environ.get(ZMQ_BACKEND_ENV, ZMQ_BACKEND_PYZMQ).strip().lower()
    if not backend:
        return ZMQ_BACKEND_PYZMQ
    if backend not in ZMQ_BACKENDS:
        choices = ", ".join(sorted(ZMQ_BACKENDS))
        raise ValueError(
            f"Unsupported ZMQ backend {backend!r}. Set {ZMQ_BACKEND_ENV} to one of: {choices}."
        )
    return backend


def _load_backend() -> tuple[str, _t.Any, _t.Any]:
    backend = _backend_name()
    try:
        if backend == ZMQ_BACKEND_PYOMQ:
            import pyomq as zmq
            import pyomq.asyncio as zmq_asyncio
        else:
            import zmq
            import zmq.asyncio as zmq_asyncio
    except ImportError as e:
        raise ZMQBackendImportError(
            f"Failed to import {backend!r} ZMQ backend selected by {ZMQ_BACKEND_ENV}."
        ) from e
    return backend, zmq, zmq_asyncio


zmq_backend, zmq, zmq_asyncio = _load_backend()
