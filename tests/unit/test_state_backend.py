"""Unit tests for `StateBackend` class."""

from contextlib import AbstractContextManager, nullcontext
import typing as _t

import pytest
import time_machine

from plugboard.state import (
    DictStateBackend,
    RayStateBackend,
    StateBackend,
)
from plugboard.utils.entities import EntityIdGen


@pytest.fixture(scope="module")
def datetime_now() -> str:
    """Creates current time string."""
    return "2024-10-04T12:00:00+00:00"


@pytest.fixture(scope="module")
def null_job_id() -> None:
    """A null job id."""
    return None


@pytest.fixture(scope="module")
def valid_job_id() -> str:
    """An existing valid job id."""
    return EntityIdGen.job_id()


@pytest.fixture(scope="module")
def invalid_job_id() -> str:
    """An invalid job id."""
    return "invalid_job_id"


@pytest.fixture(scope="module", params=[DictStateBackend, RayStateBackend])
def state_backend_cls(request: pytest.FixtureRequest) -> _t.Type[StateBackend]:
    """Returns a `StateBackend` class."""
    return request.param


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job_id_fixture, metadata, exc_ctx",
    [
        ("null_job_id", None, None),
        ("null_job_id", {"key": "value"}, None),
        ("valid_job_id", {"key": "value"}, None),
        ("invalid_job_id", None, pytest.raises(ValueError)),
    ],
)
async def test_state_backend_init(
    datetime_now: str,
    state_backend_cls: _t.Type[StateBackend],
    job_id_fixture: str,
    metadata: _t.Optional[dict],
    exc_ctx: AbstractContextManager,
    request: pytest.FixtureRequest,
) -> None:
    """Tests `StateBackend` initialisation."""
    job_id: _t.Optional[str] = request.getfixturevalue(job_id_fixture)

    state_backend = state_backend_cls(job_id=job_id, metadata=metadata)

    with exc_ctx or nullcontext():
        with time_machine.travel(datetime_now, tick=False):
            await state_backend.init()

    if exc_ctx is not None:
        return

    assert state_backend.created_at == datetime_now

    assert state_backend.job_id is not None
    assert EntityIdGen.is_job_id(state_backend.job_id)
    if job_id is not None:
        assert state_backend.job_id == job_id

    assert state_backend.metadata == (metadata or dict())


@pytest.mark.asyncio
async def test_state_backend_init_with_existing_job(
    datetime_now: str,
    state_backend_cls: _t.Type[StateBackend],
    valid_job_id: str,
) -> None:
    """Tests `StateBackend` initialisation with an existing job_id."""
    # Initialise once to create the job
    state_backend1 = state_backend_cls(job_id=valid_job_id, metadata={"original": "data"})
    with time_machine.travel(datetime_now, tick=False):
        await state_backend1.init()
    assert state_backend1.metadata == {"original": "data"}

    # Initialise again with the same job_id and new metadata
    state_backend2 = state_backend_cls(
        job_id=valid_job_id, metadata={"new": "data", "original": "updated"}
    )
    with time_machine.travel(datetime_now, tick=False):
        await state_backend2.init()

    # The metadata should be merged
    assert state_backend2.metadata == {"original": "updated", "new": "data"}


@pytest.mark.asyncio
async def test_state_backend_get(state_backend_cls: _t.Type[DictStateBackend]) -> None:
    """Tests `StateBackend` get method."""
    state_backend = state_backend_cls()

    # Test getting a value that exists in the state
    state_backend._state = {"key": "value"}
    result = await state_backend._get("key")
    assert result == "value"

    # Test getting a value that does not exist in the state
    result = await state_backend._get("nonexistent_key")
    assert result is None

    # Test getting a nested value that exists in the state
    state_backend._state = {"nested": {"key": "value"}}
    result = await state_backend._get(("nested", "key"))
    assert result == "value"

    # Test getting a nested value where the intermediate key does not exist
    result = await state_backend._get(("nonexistent", "key"))
    assert result is None

    # Test getting a nested value where the final key does not exist
    result = await state_backend._get(("nested", "nonexistent_key"))
    assert result is None


@pytest.mark.asyncio
async def test_state_backend_set(state_backend_cls: _t.Type[DictStateBackend]) -> None:
    """Tests `StateBackend` set method."""
    state_backend = state_backend_cls()

    # Test setting a value with a single key
    await state_backend._set("key", "value")
    assert state_backend._state == {"key": "value"}

    # Test setting a value with a nested key
    await state_backend._set(("nested", "key"), "value")
    assert state_backend._state == {"key": "value", "nested": {"key": "value"}}

    # Test setting a value with a nested key where the intermediate key does not exist
    await state_backend._set(("nonexistent", "key"), "value")
    assert state_backend._state == {
        "key": "value",
        "nested": {"key": "value"},
        "nonexistent": {"key": "value"},
    }

    # Test setting a value with a nested key where the final key already exists
    await state_backend._set(("nested", "key"), "new_value")
    assert state_backend._state == {
        "key": "value",
        "nested": {"key": "new_value"},
        "nonexistent": {"key": "value"},
    }


@pytest.mark.asyncio
async def test_state_backend_id_methods(
    state_backend_cls: _t.Type[StateBackend], valid_job_id: str
) -> None:
    """Tests `_get_db_id` and `_strip_job_id` methods."""
    state_backend = state_backend_cls(job_id=valid_job_id)
    await state_backend.init()

    # _get_db_id
    with pytest.raises(ValueError, match="Invalid entity id:"):
        state_backend._get_db_id("a:b:c")
    with pytest.raises(ValueError, match="does not belong to job"):
        state_backend._get_db_id("wrong_job:entity")

    # _strip_job_id
    with pytest.raises(ValueError, match="Invalid database id:"):
        state_backend._strip_job_id("a")
    with pytest.raises(ValueError, match="Invalid database id:"):
        state_backend._strip_job_id("a:b:c")
    with pytest.raises(ValueError, match="does not belong to job"):
        state_backend._strip_job_id(f"wrong_job:{valid_job_id}")
