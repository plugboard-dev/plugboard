"""Provides `ProcessSpec` class."""

import typing as _t

from pydantic import BaseModel

from .component import ComponentSpec
from .connector import ConnectorSpec
from .state import StateBackendSpec


class ProcessArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`Process`][plugboard.process.Process] constructor arguments.

    Attributes:
        components: Specifies each `Component` in the `Process`.
        connectors: Specifies the connections between each `Component`.
        parameters: Optional; Parameters for the `Process`.
        state: Optional; Specifies the `StateBackend` used for the `Process`.
    """

    components: _t.Optional[list[ComponentSpec]] = None
    connectors: _t.Optional[list[ConnectorSpec]] = None
    parameters: _t.Optional[dict] = None
    state: _t.Optional[StateBackendSpec] = None


class ProcessSpec(BaseModel):
    """Specification of a Plugboard [`Process`][plugboard.process.Process].

    Attributes:
        args: The arguments for the `Process`.
    """

    args: ProcessArgsSpec
