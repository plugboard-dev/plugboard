"""Provides `StateBackendSpec` class."""

from datetime import datetime, timezone
import typing as _t

from pydantic import BaseModel, Field

from plugboard.schemas.entities import Entity


DEFAULT_STATE_BACKEND_CLS_PATH: str = "plugboard.state.DictStateBackend"


class StateBackendArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        parameters: Parameters for the `StateBackend`.
    """

    job_id: _t.Optional[str] = Field(default=None, pattern=Entity.Job.id_regex)
    parameters: dict = {}


class StateBackendSpec(BaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str = DEFAULT_STATE_BACKEND_CLS_PATH
    args: StateBackendArgsSpec = StateBackendArgsSpec()


class StateSchema(BaseModel):
    """Schema for Plugboard state data."""

    job_id: str = Field(pattern=Entity.Job.id_regex)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
