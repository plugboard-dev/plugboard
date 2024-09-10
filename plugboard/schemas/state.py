"""Provides `StateBackendSpec` class."""

import typing as _t

from pydantic import BaseModel


class StateBackendArgsSpec(BaseModel, extra="allow"):
    """Specification of the `StateBackend` constructor arguments."""

    parameters: _t.Optional[dict] = None


class StateBackendSpec(BaseModel):
    """Specification of a Plugboard `StateBackend`."""

    type: str
    args: StateBackendArgsSpec
