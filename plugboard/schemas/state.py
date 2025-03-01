"""Provides `StateBackendSpec` class."""

from datetime import datetime, timezone
import re
import typing as _t

from pydantic import ConfigDict, Field, field_validator, with_config

from plugboard.schemas._common import PlugboardBaseModel
from plugboard.schemas.entities import Entity


DEFAULT_STATE_BACKEND_CLS_PATH: str = "plugboard.state.DictStateBackend"


@with_config(ConfigDict(extra="allow"))
class StateBackendArgsSpec(_t.TypedDict):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        job_id: Optional; The unique id for the job.
        metadata: Optional; Metadata for a run.
    """

    job_id: _t.NotRequired[str | None]
    metadata: _t.NotRequired[dict[str, _t.Any] | None]


class StateBackendSpec(PlugboardBaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str = DEFAULT_STATE_BACKEND_CLS_PATH
    args: StateBackendArgsSpec = StateBackendArgsSpec()

    # Required for https://github.com/pydantic/pydantic/issues/11510
    @field_validator("args")
    @classmethod
    def _validate_args(cls, v: StateBackendArgsSpec) -> StateBackendArgsSpec:
        # Check that job_id matches Entity.Job.id_regex
        if job_id := v.get("job_id"):
            if re.match(Entity.Job.id_regex, job_id) is None:
                raise ValueError(f"Invalid job_id: {job_id}")
        return v


class StateSchema(PlugboardBaseModel):
    """Schema for Plugboard state data."""

    job_id: str = Field(pattern=Entity.Job.id_regex)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = {}
