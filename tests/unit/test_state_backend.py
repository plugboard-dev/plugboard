"""Unit tests for `StateBackend` class."""

from contextlib import AbstractContextManager, nullcontext
import typing as _t

import pytest
import time_machine

from plugboard.state import DictStateBackend
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job_id_fixture, metadata, exc_ctx",
    [
        ("null_job_id", None, None),
        ("valid_job_id", {"key": "value"}, None),
        ("invalid_job_id", None, pytest.raises(ValueError)),
    ],
)
async def test_state_backend_init(
    datetime_now: str,
    job_id_fixture: str,
    metadata: _t.Optional[dict],
    exc_ctx: AbstractContextManager,
    request: pytest.FixtureRequest,
) -> None:
    """Tests `StateBackend` initialisation."""
    job_id: _t.Optional[str] = request.getfixturevalue(job_id_fixture)

    state_backend = DictStateBackend(job_id=job_id, metadata=metadata)

    with exc_ctx or nullcontext():
        with time_machine.travel(datetime_now, tick=False):
            await state_backend.init()

    if exc_ctx is not None:
        return

    assert await state_backend.created_at == datetime_now

    assert await state_backend.job_id is not None
    assert EntityIdGen.is_job_id(await state_backend.job_id)
    if job_id is not None:
        assert await state_backend.job_id == job_id

    assert await state_backend.metadata == (metadata or dict())
