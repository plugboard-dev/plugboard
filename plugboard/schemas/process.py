"""Provides `ProcessSpec` class."""

import typing as _t

from annotated_types import Len
from pydantic import model_validator
from typing_extensions import Self

from plugboard.schemas._common import PlugboardBaseModel
from .component import ComponentSpec
from .connector import DEFAULT_CHANNEL_CLS_PATH, ChannelBuilderSpec, ConnectorSpec
from .state import StateBackendSpec


class ProcessArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`Process`][plugboard.process.Process] constructor arguments.

    Attributes:
        components: Specifies each `Component` in the `Process`.
        connectors: Specifies the connections between each `Component`.
        name: Unique identifier for `Process`.
        parameters: Parameters for the `Process`.
        state: Optional; Specifies the `StateBackend` used for the `Process`.
    """

    components: _t.Annotated[list[ComponentSpec], Len(min_length=1)]
    connectors: list[ConnectorSpec] = []
    name: _t.Optional[str] = None
    parameters: dict = {}
    state: StateBackendSpec = StateBackendSpec()


class ProcessSpec(PlugboardBaseModel):
    """Specification of a Plugboard [`Process`][plugboard.process.Process].

    Attributes:
        args: The arguments for the `Process`.
        channel_builder: The `ChannelBuilder` to use for the `Process`.
    """

    args: ProcessArgsSpec
    type: _t.Literal[
        "plugboard.process.SingleProcess",
        "plugboard.process.ParallelProcess",
    ] = "plugboard.process.SingleProcess"
    channel_builder: ChannelBuilderSpec = ChannelBuilderSpec()

    @model_validator(mode="after")
    def _validate_channel_builder_type(self: Self) -> Self:
        channel_builder_type = self.channel_builder.type
        if (
            self.type.endswith("ParallelProcess")
            and channel_builder_type == DEFAULT_CHANNEL_CLS_PATH
        ):
            raise ValueError("ParallelProcess requires a parallel-capable channel builder type.")
        return self
