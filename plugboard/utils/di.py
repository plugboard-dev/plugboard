"""Provides a dependency injection container and utils."""

import multiprocessing
import sys
import typing as _t

from that_depends import BaseContainer
from that_depends.providers import Resource, Singleton

from plugboard.connector._zmq import ZMQProxy
from plugboard.utils.settings import Settings


_ZMQ_PROXY: _t.Optional[ZMQProxy] = None


def _mp_set_start_method(use_fork: bool = False) -> _t.Iterator[None]:
    print("Setting multiprocessing start method")
    multiprocessing.get_context(method="fork" if use_fork else "spawn")
    yield


def _zmq_proxy_lifecycle() -> _t.Iterator[ZMQProxy]:
    global _ZMQ_PROXY
    _ZMQ_PROXY = ZMQProxy()
    _t.cast(ZMQProxy, _ZMQ_PROXY)
    try:
        print("Starting ZMQ proxy...", file=sys.stdout, flush=True)
        yield _ZMQ_PROXY
    finally:
        print("Terminating ZMQ proxy...", file=sys.stdout, flush=True)
        _ZMQ_PROXY.terminate()
        print("Terminated ZMQ proxy.", file=sys.stdout, flush=True)


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
    mp_ctx: Resource[None] = Resource(_mp_set_start_method, settings.flags.multiprocessing_fork)
    zmq_proxy: Resource[ZMQProxy] = Resource(_zmq_proxy_lifecycle)


DI.mp_ctx.sync_resolve()
