"""Provides a dependency injection container and utils."""

import multiprocessing
import sys
import typing as _t

from that_depends import BaseContainer
from that_depends.providers import Resource, Singleton

from plugboard.connector import _zmq
from plugboard.utils.settings import Settings


def _mp_set_start_method(use_fork: bool = False) -> _t.Iterator[None]:
    print("Setting multiprocessing start method")
    try:
        multiprocessing.get_context(method="fork" if use_fork else "spawn")
    except ValueError:
        print("Failed to set multiprocessing start method", file=sys.stderr, flush=True)
        pass
    yield


def _zmq_proxy_lifecycle(mp_ctx: Resource[None]) -> _t.Iterator[_zmq.ZMQProxy]:
    if _zmq.ZMQ_PROXY is None:
        _zmq.ZMQ_PROXY = _zmq.ZMQProxy()
    zmq_proxy = _t.cast(_zmq.ZMQProxy, _zmq.ZMQ_PROXY)
    try:
        print("Starting ZMQ proxy...", file=sys.stdout, flush=True)
        yield zmq_proxy
    finally:
        print("Terminating ZMQ proxy...", file=sys.stdout, flush=True)
        if _zmq.ZMQ_PROXY is not None:
            _zmq.ZMQ_PROXY.terminate()
            _zmq.ZMQ_PROXY = None
        print("Terminated ZMQ proxy.", file=sys.stdout, flush=True)


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
    mp_ctx: Resource[None] = Resource(_mp_set_start_method, settings.flags.multiprocessing_fork)
    zmq_proxy: Resource[_zmq.ZMQProxy] = Resource(_zmq_proxy_lifecycle, mp_ctx)
