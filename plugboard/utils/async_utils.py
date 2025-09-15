"""Provides utilities for working with asynchronous code."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import typing as _t


try:
    from uvloop import run as _asyncio_run
except ImportError:  # pragma: no cover
    from asyncio import run as _asyncio_run


async def gather_except(*coros: _t.Coroutine) -> list[_t.Any]:
    """Attempts to gather the given coroutines, raising any exceptions."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    if exceptions:
        raise ExceptionGroup("One or more exceptions occurred in coroutines", exceptions)
    return results


def _run_coro_in_thread(coro: _t.Coroutine, timeout: _t.Optional[float] = None) -> _t.Any:
    def _target() -> _t.Any:
        return _asyncio_run(coro)

    with ThreadPoolExecutor() as pool:
        future = pool.submit(_target)
        return future.result(timeout=timeout)


def run_coro_sync(coro: _t.Coroutine, timeout: _t.Optional[float] = None) -> _t.Any:
    """Runs a coroutine synchronously, returning the result.

    This is useful for async code run from synchronous CLI entrypoints. In the
    test environment, it will run the coroutine in the current event loop, if
    present, otherwise it will create a new event loop for the coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover
        # No loop running in current thread
        return _asyncio_run(coro)

    if loop.is_running():
        # Run coroutine in new thread with dedicated event loop.
        return _run_coro_in_thread(coro, timeout=timeout)

    # loop was obtained but is not running.
    return loop.run_until_complete(coro)  # pragma: no cover
