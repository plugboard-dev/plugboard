"""Provides retry and backoff helpers for long-lived connections."""

import asyncio
from collections.abc import Awaitable, Callable
import typing as _t

import msgspec
import structlog

from plugboard.exceptions import MessageBrokerPermanentError, NoMoreDataException


_T = _t.TypeVar("_T")


class RetryPolicy(msgspec.Struct, frozen=True):
    """Exponential backoff parameters for a retryable operation.

    The three values always travel together and drive a single backoff formula, so
    they are grouped into one immutable value object.

    Attributes:
        max_retries: Number of times to retry after a failure, so the operation runs
            at most `max_retries + 1` times.
        base_delay: Base delay in seconds, doubled on each consecutive attempt.
        max_delay: Upper bound for the delay between attempts.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0

    def delay_for(self, attempt: int) -> float:
        """Calculates the delay to wait after the given zero-based attempt failed.

        Args:
            attempt: The zero-based index of the attempt that failed.

        Returns:
            The backoff delay in seconds, capped by `max_delay`.
        """
        return min(self.base_delay * (2**attempt), self.max_delay)


async def attempt_reconnect(
    connect: Callable[[], Awaitable[None]],
    disconnect: Callable[[], Awaitable[None]],
    *,
    logger: structlog.BoundLogger,
    topic: str,
) -> None:
    """Re-establishes a message broker connection by disconnecting then connecting.

    A failure to disconnect is logged and ignored: the connection is assumed to be
    broken already, and the new connection attempt is what matters. A failure to
    connect propagates so the caller can count it as another failed attempt.

    Args:
        connect: The coroutine function that establishes the connection.
        disconnect: The coroutine function that closes the connection.
        logger: Logger to report reconnection progress to.
        topic: The topic/queue being connected to, used for log context.
    """
    logger.info("Attempting reconnection to message broker", topic=topic)
    try:
        await disconnect()
    except Exception as error:  # noqa: BLE001
        logger.warning("Error during disconnect in reconnection", error=str(error))
    await connect()
    logger.info("Reconnected to message broker", topic=topic)


async def _backoff_and_reconnect(
    policy: RetryPolicy,
    logger: structlog.BoundLogger,
    description: str,
    attempt: int,
    error: Exception,
    reconnect: Callable[[], Awaitable[None]],
) -> None:
    """Waits out the backoff delay for a failed attempt and then reconnects.

    A failing reconnect is recorded and swallowed: the next attempt may succeed, and
    the caller raises the broker error once the attempts are used up. Without this the
    reconnect error would escape the retry loop on the first transient failure.
    """
    delay = policy.delay_for(attempt)
    logger.warning(
        f"Transient error {description}, retrying",
        attempt=attempt + 1,
        delay=delay,
        error=str(error),
    )
    await asyncio.sleep(delay)
    try:
        await reconnect()
    except Exception as reconnect_error:  # noqa: BLE001
        logger.warning(
            f"Reconnection during {description} failed",
            attempt=attempt + 1,
            error=str(reconnect_error),
        )


async def with_retry(
    operation: Callable[[], Awaitable[_T]],
    reconnect: Callable[[], Awaitable[None]],
    *,
    policy: RetryPolicy,
    logger: structlog.BoundLogger,
    description: str,
) -> _T:
    """Runs an operation, retrying transient failures with backoff and reconnection.

    Only transient failures are retried: `NoMoreDataException` means the source is
    exhausted and `MessageBrokerPermanentError` means retrying cannot help, so both
    propagate immediately.

    Args:
        operation: The coroutine function to run.
        reconnect: The coroutine function to call between attempts.
        policy: Backoff parameters, including the retry bound.
        logger: Logger to report transient failures to.
        description: Human-readable name of the operation, used in log messages.

    Returns:
        Whatever `operation` returns.

    Raises:
        NoMoreDataException: If the source is exhausted.
        MessageBrokerPermanentError: If the failure is not retryable.
        Exception: The error raised by the final attempt, if every attempt failed.
    """
    for attempt in range(policy.max_retries):
        try:
            return await operation()
        except (NoMoreDataException, MessageBrokerPermanentError):
            raise
        except Exception as error:  # noqa: BLE001
            await _backoff_and_reconnect(policy, logger, description, attempt, error, reconnect)
    # Final attempt: no backoff, so its error propagates unchanged.
    return await operation()
