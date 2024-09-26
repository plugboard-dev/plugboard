"""Provides `StateBackendSpec` class."""

from pydantic import BaseModel, Field

from plugboard.schemas.entities import Entity


class StateBackendArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        parameters: Parameters for the `StateBackend`.
    """

    parameters: dict = {}


class StateBackendSpec(BaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str
    args: StateBackendArgsSpec


class StateSchema(BaseModel):
    """Schema for Plugboard state data."""

    job_id: str = Field(pattern=Entity.Job.id_regex)
