"""Provides `StateBackendSpec` class."""

from datetime import datetime, timezone
import typing as _t

from pydantic import ConfigDict, Field, with_config

from plugboard.schemas._common import PlugboardBaseModel
from plugboard.schemas.entities import Entity


DEFAULT_STATE_BACKEND_CLS_PATH: str = "plugboard.state.DictStateBackend"


@with_config(ConfigDict(extra="allow"))
class StateBackendArgsSpec(_t.TypedDict):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        job_id: The unique id for the job.
        metadata: Metadata for a run.
    """

    job_id: _t.Annotated[_t.Optional[str], Field(default=None, pattern=Entity.Job.id_regex)]
    metadata: _t.Annotated[dict[str, _t.Any], Field(default_factory=dict)]


class StateBackendSpec(PlugboardBaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str = DEFAULT_STATE_BACKEND_CLS_PATH
    args: StateBackendArgsSpec = StateBackendArgsSpec(job_id=None, metadata={})


class StateSchema(PlugboardBaseModel):
    """Schema for Plugboard state data."""

    job_id: str = Field(pattern=Entity.Job.id_regex)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = {}
