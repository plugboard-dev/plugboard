"""Provides `ProcessSpec` class."""

from pydantic import BaseModel

from .component import ComponentSpec
from .connector import ConnectorSpec
from .state import StateBackendSpec


class ProcessSpec(BaseModel):
    """Specification of a Plugboard `Process`."""

    # TODO: do we need a name, i.e. for nested processes?
    type: str
    components: list[ComponentSpec]
    connectors: list[ConnectorSpec]
    parameters: dict
    state: StateBackendSpec
