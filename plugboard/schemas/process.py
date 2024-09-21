"""Provides `ProcessSpec` class."""

import typing as _t

from pydantic import BaseModel

from .component import ComponentSpec
from .connector import ChannelBuilderSpec, ConnectorSpec
from .state import StateBackendSpec


class ProcessArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`Process`][plugboard.process.Process] constructor arguments.

    Attributes:
        components: Specifies each `Component` in the `Process`.
        connectors: Specifies the connections between each `Component`.
        parameters: Parameters for the `Process`.
        state: Optional; Specifies the `StateBackend` used for the `Process`.
    """

    components: list[ComponentSpec] = []
    connectors: list[ConnectorSpec] = []
    parameters: dict = {}
    state: _t.Optional[StateBackendSpec] = None


class ProcessSpec(BaseModel):
    """Specification of a Plugboard [`Process`][plugboard.process.Process].

    Attributes:
        args: The arguments for the `Process`.
        channel_builder: The `ChannelBuilder` to use for the `Process`.
    """

    args: ProcessArgsSpec
    channel_builder: ChannelBuilderSpec = ChannelBuilderSpec(
        type="plugboard.connector.AsyncioChannelBuilder"
    )
