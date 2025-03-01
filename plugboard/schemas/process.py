"""Provides `ProcessSpec` class."""

import typing as _t

from pydantic import ConfigDict, Field, model_validator, with_config
from typing_extensions import Self

from plugboard.schemas._common import PlugboardBaseModel
from .component import ComponentSpec
from .connector import DEFAULT_CONNECTOR_CLS_PATH, ConnectorBuilderSpec, ConnectorSpec
from .state import StateBackendSpec


@with_config(ConfigDict(extra="allow"))
class ProcessArgsSpec(_t.TypedDict):
    """Specification of the [`Process`][plugboard.process.Process] constructor arguments.

    Attributes:
        components: Specifies each `Component` in the `Process`.
        connectors: Specifies the connections between each `Component`.
        name: Optional; Unique identifier for `Process`.
        parameters: Parameters for the `Process`.
        state: Optional; Specifies the `StateBackend` used for the `Process`.
    """

    components: _t.Annotated[list[ComponentSpec], Field(min_length=1)]
    connectors: _t.Annotated[list[ConnectorSpec], Field(default_factory=list)]
    name: _t.NotRequired[str | None]
    parameters: _t.Annotated[dict[str, _t.Any], Field(default_factory=dict)]
    state: _t.Annotated[StateBackendSpec, Field(default_factory=StateBackendSpec)]


class ProcessSpec(PlugboardBaseModel):
    """Specification of a Plugboard [`Process`][plugboard.process.Process].

    Attributes:
        args: The arguments for the `Process`.
        type: The type of `Process` to build.
        connector_builder: The `ConnectorBuilder` to use for the `Process`.
    """

    args: ProcessArgsSpec
    type: _t.Literal[
        "plugboard.process.LocalProcess",
        "plugboard.process.RayProcess",
    ] = "plugboard.process.LocalProcess"
    connector_builder: ConnectorBuilderSpec = ConnectorBuilderSpec()

    @model_validator(mode="after")
    def _validate_channel_builder_type(self: Self) -> Self:
        if (
            self.type.endswith("RayProcess")
            and self.connector_builder.type == DEFAULT_CONNECTOR_CLS_PATH
        ):
            raise ValueError("RayProcess requires a parallel-capable connector type.")
        return self
