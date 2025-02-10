"""Provides a dependency injection container and utils."""

import multiprocessing
import typing as _t

from that_depends import BaseContainer
from that_depends.providers import Resource, Singleton

from plugboard.connector._zmq import ZMQProxy
from plugboard.utils.settings import Settings


def _mp_set_start_method(use_fork: bool = False) -> None:
    multiprocessing.set_start_method("fork" if use_fork else "spawn")


def _zmq_proxy_lifecycle() -> _t.Iterator[ZMQProxy]:
    zmq_proxy = ZMQProxy()
    try:
        yield zmq_proxy
    finally:
        zmq_proxy.terminate()


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
    mp_ctx: Singleton[None] = Singleton(_mp_set_start_method, settings.flags.multiprocessing_fork)
    zmq_proxy: Resource[ZMQProxy] = Resource(_zmq_proxy_lifecycle)
