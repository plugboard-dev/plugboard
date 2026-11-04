"""Tests for failure propagation and cancellation of actual Ray actor calls."""

import asyncio

import pytest
import ray

from plugboard.process.ray_process import _gather


@ray.remote
class WaitingActor:
    """Actor with a blocked call and observable cancellation."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def wait(self) -> None:
        """Wait indefinitely until cancelled."""
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()

    async def wait_started(self) -> None:
        """Wait for the blocked call to begin."""
        await self.started.wait()

    async def wait_cancelled(self) -> None:
        """Wait for remote cancellation cleanup."""
        await self.cancelled.wait()

    async def fail(self) -> None:
        """Fail after the blocked call has started."""
        await self.started.wait()
        raise ValueError("actor failed")

    async def echo(self, value: int) -> int:
        """Return a value for ordered result checks."""
        return value


@pytest.mark.parametrize("remote_failure", [False, True])
async def test_gather_cancels_remote_sibling(ray_ctx: None, remote_failure: bool) -> None:
    """Both local and remote failures must cancel blocked remote work."""
    actor = WaitingActor.remote()

    async def fail_locally() -> None:
        await actor.wait_started.remote()
        raise ValueError("local failed")

    try:
        async with asyncio.timeout(15):
            with pytest.raises(ExceptionGroup) as exc_info:
                await _gather(
                    actor.wait.remote(),
                    actor.fail.remote() if remote_failure else fail_locally(),
                )
            assert len(exc_info.value.exceptions) == 1
            assert isinstance(exc_info.value.exceptions[0], ValueError)
            await actor.wait_cancelled.remote()
    finally:
        ray.kill(actor)


async def test_gather_caller_cancellation_cancels_remote_work(ray_ctx: None) -> None:
    """Cancelling the driver task must cancel the actor call as well."""
    actor = WaitingActor.remote()
    try:
        async with asyncio.timeout(15):
            task = asyncio.create_task(_gather(actor.wait.remote()))
            await actor.wait_started.remote()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await actor.wait_cancelled.remote()
    finally:
        ray.kill(actor)


async def test_gather_mixed_results(ray_ctx: None) -> None:
    """Gather local coroutines and ObjectRefs together, retaining input order."""
    actor = WaitingActor.remote()

    async def local() -> int:
        return 2

    try:
        async with asyncio.timeout(15):
            assert await _gather(actor.echo.remote(1), local(), actor.echo.remote(3)) == [1, 2, 3]
    finally:
        ray.kill(actor)
