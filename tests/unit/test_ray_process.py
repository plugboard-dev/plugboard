"""Tests for TaskGroup coordination in RayProcess."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugboard.process import RayProcess
from plugboard.process.ray_process import _gather
from plugboard.schemas import Status


async def test_gather_preserves_result_order() -> None:
    """Return results in input order even when completion order differs."""
    ready = asyncio.Event()

    async def first() -> int:
        await ready.wait()
        return 1

    async def second() -> int:
        ready.set()
        return 2

    assert await _gather(first(), second()) == [1, 2]
    assert await _gather() == []


async def test_gather_cancels_siblings_on_failure() -> None:
    """A failure must propagate without waiting for an indefinitely blocked sibling."""
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def blocked() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def fail() -> None:
        await started.wait()
        raise ValueError("component failed")

    async with asyncio.timeout(5):
        with pytest.raises(ExceptionGroup) as exc_info:
            await _gather(blocked(), fail())

    assert stopped.is_set()
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)


@pytest.mark.parametrize("unresponsive", [False, True])
async def test_step_preserves_original_failure(
    monkeypatch: pytest.MonkeyPatch, unresponsive: bool
) -> None:
    """A failed or blocked attribute refresh must not obscure the step failure."""
    process = object.__new__(RayProcess)
    component = MagicMock()
    component.id = "component"
    actor = MagicMock()
    actor.step.remote = AsyncMock(side_effect=ValueError("step failed"))

    async def refresh() -> None:
        if unresponsive:
            await asyncio.Event().wait()
        raise RuntimeError("refresh failed")

    actor.dict.remote = refresh
    process._component_actors = {component.id: actor}
    process.components = {component.id: component}
    process._is_initialised = True
    process._state_is_connected = False
    process._state = MagicMock()
    process._logger = MagicMock()
    monkeypatch.setattr("plugboard.process.ray_process._ATTRIBUTE_UPDATE_TIMEOUT_SECONDS", 0.01)

    async with asyncio.timeout(5):
        with pytest.raises(ExceptionGroup) as exc_info:
            await process.step()

    assert process.status == Status.FAILED
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "step failed"
    process._logger.warning.assert_called_once()


async def test_gather_propagates_caller_cancellation() -> None:
    """Cancelling the caller cleans up local siblings and propagates CancelledError."""
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def blocked() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async with asyncio.timeout(5):
        task = asyncio.create_task(_gather(blocked()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stopped.is_set()
