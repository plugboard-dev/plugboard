"""Provides `ProcessSpec` class."""

import typing as _t

from annotated_types import Len
from pydantic import field_validator, model_validator
from typing_extensions import Self

from plugboard.schemas._common import PlugboardBaseModel
from .component import ComponentSpec
from .connector import DEFAULT_CONNECTOR_CLS_PATH, ConnectorBuilderSpec, ConnectorSpec
from .state import StateBackendSpec


class ProcessArgsDict(_t.TypedDict):
    """`TypedDict` of the [`Process`][plugboard.process.Process] constructor arguments."""

    components: list[ComponentSpec]
    connectors: list[ConnectorSpec]
    name: _t.NotRequired[str | None]
    parameters: dict[str, _t.Any]
    state: _t.NotRequired[StateBackendSpec | None]


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
    parameters: dict[str, _t.Any] = {}
    state: StateBackendSpec = StateBackendSpec()


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

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, value: _t.Any) -> str:
        if isinstance(value, str):
            return {
                "plugboard.process.local_process.LocalProcess": "plugboard.process.LocalProcess",
                "plugboard.process.ray_process.RayProcess": "plugboard.process.RayProcess",
            }.get(value, value)
        return value
