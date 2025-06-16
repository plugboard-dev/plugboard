"""Provides a dependency injection container and utils."""

import multiprocessing
import os
import typing as _t

import aio_pika
import structlog
from that_depends import BaseContainer, ContextScopes, fetch_context_item
from that_depends.providers import ContextResource, Resource, Singleton
from yarl import URL

from plugboard._zmq.zmq_proxy import ZMQProxy
from plugboard.utils.entities import EntityIdGen
from plugboard.utils.logging import configure_logging
from plugboard.utils.settings import Settings


def _logger(settings: Settings) -> structlog.BoundLogger:
    configure_logging(settings)
    return structlog.get_logger()


def _mp_set_start_method(
    logger: Singleton[structlog.BoundLogger], use_fork: bool = False
) -> _t.Iterator[None]:
    try:
        method = "fork" if use_fork else "spawn"
        multiprocessing.get_context(method=method)
        logger.debug(f"Set multiprocessing start method to {method}")
    except ValueError:  # pragma: no cover
        logger.warning("Failed to set multiprocessing start method")
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
        except RuntimeError as e:  # pragma: no cover
            logger.warning(f"Error during ZMQProxy termination: {e}")


async def _rabbitmq_conn(
    logger: Singleton[structlog.BoundLogger], url: _t.Optional[str] = None
) -> _t.AsyncIterator[aio_pika.abc.AbstractRobustConnection]:
    url = url or "amqp://user:password@localhost:5672/"
    try:
        conn = await aio_pika.connect_robust(URL(url))
        yield conn
    except aio_pika.exceptions.AMQPConnectionError as e:  # pragma: no cover
        logger.error(f"Failed to connect to RabbitMQ: {e}")
    finally:  # pragma: no cover
        try:
            await conn.close()
        except UnboundLocalError:
            pass


def _job_id() -> _t.Iterator[str]:
    """Returns a job ID which uniquely identifies the current plugboard run.

    If a job ID is available in the context (from the cli, the state spec, or an argument to the
    StateBackend), it will take precedence. If the job ID is set in the env var `PLUGBOARD_JOB_ID`,
    it will be checked against the one in the context, if present. If they do not match, a
    RuntimeError will be raised. If the job ID is not set in the context or the env var, a new
    unique job ID will be generated.
    """
    arg_job_id = fetch_context_item("job_id")
    env_job_id = os.environ.get("PLUGBOARD_JOB_ID")
    if arg_job_id is not None:
        if env_job_id is not None and arg_job_id != env_job_id:
            raise RuntimeError(
                f"Job ID {arg_job_id} does not match environment variable "
                f"PLUGBOARD_JOB_ID={env_job_id}"
            )
        job_id = arg_job_id
    elif env_job_id is not None:
        job_id = env_job_id
    else:
        job_id = EntityIdGen.job_id()
    if not EntityIdGen.is_job_id(job_id):
        raise ValueError(f"Invalid job ID: {job_id}.")
    yield job_id


class DI(BaseContainer):
    """`DI` is a dependency injection container for plugboard."""

    default_scope = ContextScopes.APP

    settings: Singleton[Settings] = Singleton(Settings)
    logger: Singleton[structlog.BoundLogger] = Singleton(_logger, settings.cast)
    mp_ctx: Resource[None] = Resource(
        _mp_set_start_method, logger, use_fork=settings.flags.multiprocessing_fork
    )
    zmq_proxy: Resource[ZMQProxy] = Resource(_zmq_proxy, mp_ctx, logger)
    rabbitmq_conn: Resource[aio_pika.abc.AbstractRobustConnection] = Resource(
        _rabbitmq_conn, logger, url=settings.rabbitmq.url
    )
    job_id: ContextResource[str] = ContextResource(_job_id)
