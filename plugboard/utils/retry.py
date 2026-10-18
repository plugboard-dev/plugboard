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

    async def run(
        self,
        operation: Callable[[], Awaitable[_T]],
        reconnect: Callable[[], Awaitable[None]],
        *,
        logger: structlog.BoundLogger,
        description: str,
    ) -> _T:
        """Runs an operation, retrying transient failures with backoff and reconnection.

        Only transient failures are retried: `NoMoreDataException` means the source is
        exhausted and `MessageBrokerPermanentError` means retrying cannot help, so both
        propagate immediately. Every retry attempt re-establishes the connection before it
        runs, so the operation never relies on a connection that a failed attempt may have
        torn down. If the connection cannot be re-established, that attempt is skipped and
        the retries continue, so the connection is retried on every attempt. When all
        attempts are used up the last error is raised, so the caller sees the broker's own
        error (or the reconnect failure) rather than a synthetic "not connected" one.

        Args:
            operation: The coroutine function to run.
            reconnect: The coroutine function that re-establishes the connection.
            logger: Logger to report transient failures to.
            description: Human-readable name of the operation, used in log messages.

        Returns:
            Whatever `operation` returns.

        Raises:
            NoMoreDataException: If the source is exhausted.
            MessageBrokerPermanentError: If the failure is not retryable.
            Exception: The last error encountered, if every attempt failed.
        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                delay = self.delay_for(attempt - 1)
                logger.warning(
                    f"Transient error {description}, retrying",
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                try:
                    await reconnect()
                except Exception as reconnect_error:  # noqa: BLE001
                    # Without a connection the operation would fail with a synthetic
                    # "not connected" error, so it is skipped: the retries continue and the
                    # connection is tried again next attempt. `last_error` keeps the prior
                    # broker error, so what is eventually raised is always a real one.
                    logger.warning(
                        f"Reconnection for {description} failed, skipping attempt",
                        attempt=attempt,
                        error=str(reconnect_error),
                    )
                    continue
            try:
                return await operation()
            except (NoMoreDataException, MessageBrokerPermanentError):
                raise
            except Exception as error:  # noqa: BLE001
                last_error = error
        # Unreachable: the range is never empty, so at least one attempt ran and either
        # returned, raised a non-retryable error, or recorded the last error.
        if last_error is None:  # pragma: no cover
            raise RuntimeError("retry loop ended without recording an error")
        raise last_error


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
