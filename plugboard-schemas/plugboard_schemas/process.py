"""Provides `ProcessSpec` class."""

import typing as _t

from annotated_types import Len
from pydantic import field_validator, model_validator
from typing_extensions import Self

from ._common import PlugboardBaseModel
from .component import ComponentSpec
from .connector import (
    DEFAULT_CONNECTOR_CLS_PATH,
    RAY_CONNECTOR_CLS_PATH,
    ConnectorBuilderSpec,
    ConnectorSpec,
)
from .state import DEFAULT_STATE_BACKEND_CLS_PATH, RAY_STATE_BACKEND_CLS_PATH, StateBackendSpec


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
        parameters: Parameters for the `Process`. These will be shared across all `Component`
            objects within the `Process`.
        state: Optional; Specifies the `StateBackend` used for the `Process`.
    """

    components: _t.Annotated[list[ComponentSpec], Len(min_length=1)]
    connectors: list[ConnectorSpec] = []
    name: _t.Optional[str] = None
    parameters: dict[str, _t.Any] = {}
    state: StateBackendSpec = StateBackendSpec()

    @field_validator("parameters", mode="before")
    @classmethod
    def _coerce_parameters(cls, v: _t.Any) -> _t.Any:
        return v if v is not None else {}

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: _t.Any) -> _t.Any:
        return v if v is not None else StateBackendSpec()


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

    @model_validator(mode="after")
    def _set_default_state_backend(self: Self) -> Self:
        """Set appropriate default state backend based on process type."""
        # If RayProcess and state backend is still the default, change to RayStateBackend
        if (
            self.type == "plugboard.process.RayProcess"
            and self.args.state.type == DEFAULT_STATE_BACKEND_CLS_PATH
        ):
            self.args.state.type = RAY_STATE_BACKEND_CLS_PATH
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

    def override_process_type(self, process_type: _t.Literal["local", "ray"]) -> Self:
        """Override the process type and update connector/state to be compatible.

        Args:
            process_type: The process type to use ("local" or "ray")

        Returns:
            A new ProcessSpec with the overridden process type and compatible settings
        """
        # Map process type to full class path
        type_map = {
            "local": "plugboard.process.LocalProcess",
            "ray": "plugboard.process.RayProcess",
        }
        new_process_type = type_map[process_type]

        # Map of connector types that should be replaced
        connector_type_map = {
            "ray": {DEFAULT_CONNECTOR_CLS_PATH: RAY_CONNECTOR_CLS_PATH},
            "local": {RAY_CONNECTOR_CLS_PATH: DEFAULT_CONNECTOR_CLS_PATH},
        }

        # Map of state types that should be replaced
        state_type_map = {
            "ray": {DEFAULT_STATE_BACKEND_CLS_PATH: RAY_STATE_BACKEND_CLS_PATH},
            "local": {RAY_STATE_BACKEND_CLS_PATH: DEFAULT_STATE_BACKEND_CLS_PATH},
        }

        # Prepare updates
        updates: dict[str, _t.Any] = {"type": new_process_type}

        # Update connector if needed
        current_connector_type = self.connector_builder.type
        if current_connector_type in connector_type_map[process_type]:
            new_connector_type = connector_type_map[process_type][current_connector_type]
            updates["connector_builder"] = self.connector_builder.model_copy(
                update={"type": new_connector_type}
            )

        # Update state if needed
        current_state_type = self.args.state.type
        if current_state_type in state_type_map[process_type]:
            new_state_type = state_type_map[process_type][current_state_type]
            new_state = self.args.state.model_copy(update={"type": new_state_type})
            updates["args"] = self.args.model_copy(update={"state": new_state})

        # Apply updates and return new instance
        return self.model_copy(update=updates)
