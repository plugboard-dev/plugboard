"""Provides `StateBackendSpec` class."""

from datetime import datetime, timezone
import typing as _t

from pydantic import Field

from plugboard.schemas._common import PlugboardBaseModel
from plugboard.schemas.entities import Entity


DEFAULT_STATE_BACKEND_CLS_PATH: str = "plugboard.state.DictStateBackend"


class StateBackendArgsDict(_t.TypedDict):
    """`TypedDict` of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments."""

    job_id: _t.NotRequired[str | None]
    metadata: _t.NotRequired[dict[str, _t.Any] | None]


class StateBackendArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        job_id: The unique id for the job.
        metadata: Metadata for a run.
    """

    job_id: _t.Optional[str] = Field(default=None, pattern=Entity.Job.id_regex)
    metadata: dict[str, _t.Any] = {}


class StateBackendSpec(PlugboardBaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str = DEFAULT_STATE_BACKEND_CLS_PATH
    args: StateBackendArgsSpec = StateBackendArgsSpec()


class StateSchema(PlugboardBaseModel):
    """Schema for Plugboard state data."""

    job_id: str = Field(pattern=Entity.Job.id_regex)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = {}
