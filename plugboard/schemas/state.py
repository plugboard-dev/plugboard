"""Provides `StateBackendSpec` class."""

import typing as _t

from pydantic import BaseModel


class StateBackendArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`StateBackend`][plugboard.state.StateBackend] constructor arguments.

    Attributes:
        parameters: Optional; Parameters for the `StateBackend`.
    """

    parameters: _t.Optional[dict] = None


class StateBackendSpec(BaseModel):
    """Specification of a Plugboard [`StateBackend`][plugboard.state.StateBackend].

    Attributes:
        type: The type of the `StateBackend`.
        args: The arguments for the `StateBackend`.
    """

    type: str
    args: StateBackendArgsSpec
