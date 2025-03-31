"""Provides a dependency injection container and utils."""

import multiprocessing
import sys
import typing as _t

import structlog
from that_depends import BaseContainer
from that_depends.providers import Resource, Singleton

from plugboard._zmq.zmq_proxy import ZMQProxy
from plugboard.utils.logging import configure_logging
from plugboard.utils.settings import Settings


def _mp_set_start_method(use_fork: bool = False) -> _t.Iterator[None]:
    try:
        multiprocessing.get_context(method="fork" if use_fork else "spawn")
    except ValueError:
        print("Failed to set multiprocessing start method", file=sys.stderr, flush=True)
        pass
    yield


def _zmq_proxy(
    mp_ctx: Resource[None], logger: Singleton[structlog.BoundLogger]
) -> _t.Iterator[ZMQProxy]:
    zmq_proxy = ZMQProxy()
    try:
        yield zmq_proxy
    finally:
        try:
            zmq_proxy.terminate(timeout=5.0)
        except RuntimeError as e:
            logger.warning(f"Error during ZMQProxy termination: {e}", file=sys.stderr)


def _logger(settings: Settings) -> structlog.BoundLogger:
    configure_logging(settings)
    return structlog.get_logger()


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    settings: Singleton[Settings] = Singleton(Settings)
    logger: Singleton[structlog.BoundLogger] = Singleton(_logger, settings.cast)
    mp_ctx: Resource[None] = Resource(_mp_set_start_method, settings.flags.multiprocessing_fork)
    zmq_proxy: Resource[ZMQProxy] = Resource(_zmq_proxy, mp_ctx, logger)
