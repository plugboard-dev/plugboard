"""Provides utilities for working with asynchronous code."""

import asyncio
import typing as _t


async def gather_except(*coros: _t.Coroutine) -> list[_t.Any]:
    """Attempts to gather the given coroutines, raising any exceptions."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    if exceptions:
        raise ExceptionGroup("One or more exceptions occurred in coroutines", exceptions)
    return results
