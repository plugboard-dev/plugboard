"""Provides utilities for working with asynchronous code."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import typing as _t


async def gather_except(*coros: _t.Coroutine) -> list[_t.Any]:
    """Attempts to gather the given coroutines, raising any exceptions."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    if exceptions:
        raise ExceptionGroup("One or more exceptions occurred in coroutines", exceptions)
    return results


def run_coroutine_in_thread(coro: _t.Coroutine, timeout: float = 30) -> _t.Any:
    """Runs a coroutine in a separate thread and returns the result."""

    def _run_in_new_loop() -> _t.Any:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    with ThreadPoolExecutor() as pool:
        future = pool.submit(_run_in_new_loop)
        return future.result(timeout=timeout)
