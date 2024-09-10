"""Provides `ProcessSpec` class."""

import typing as _t

from pydantic import BaseModel

from .component import ComponentSpec
from .connector import ConnectorSpec
from .state import StateBackendSpec


class ProcessArgsSpec(BaseModel, extra="allow"):
    """Specification of the `Process` constructor arguments."""

    components: _t.List[ComponentSpec]
    connector_specs: _t.List[ConnectorSpec]
    parameters: _t.Optional[dict] = None
    state: StateBackendSpec


class ProcessSpec(BaseModel):
    """Specification of a Plugboard `Process`."""

    type: str
    components: _t.Optional[list[ComponentSpec]] = None
    connectors: _t.Optional[list[ConnectorSpec]] = None
    parameters: _t.Optional[dict] = None
    state: _t.Optional[StateBackendSpec] = None
