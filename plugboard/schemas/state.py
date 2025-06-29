"""Provides `StateBackendSpec` class."""

from datetime import datetime, timezone
from enum import StrEnum
import typing as _t

from pydantic import Field

from plugboard.schemas._common import PlugboardBaseModel
from plugboard.schemas.entities import Entity


DEFAULT_STATE_BACKEND_CLS_PATH: str = "plugboard.state.DictStateBackend"


class Status(StrEnum):
    """`Status` describes the status of either a `Component` or a `Process`.

    Attributes:
        CREATED: The `Component` or `Process` has been created but not yet started.
        INIT: The `Component` or `Process` has been initialised but has not started running.
        RUNNING: The `Component` or `Process` is currently running.
        WAITING: The `Component` or `Process` is waiting for input.
        COMPLETED: The `Component` or `Process` has completed successfully.
        FAILED: The `Component` or `Process` has failed.
        STOPPED: The `Component` or `Process` has been cancelled or stopped.
    """

    CREATED = "created"
    INIT = "init"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def is_terminal(self) -> bool:
        """Returns whether the status is terminal."""
        return self in {self.COMPLETED, self.FAILED, self.STOPPED}


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
