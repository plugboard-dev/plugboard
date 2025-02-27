"""Provides `ComponentSpec` class."""

import typing as _t

from pydantic import ConfigDict, Field

from plugboard.schemas._common import PlugboardBaseModel


class ComponentArgsSpec(_t.TypedDict):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Initial values for the `Component`.
        parameters: Parameters for the `Component`.
        constraints: Constraints for the `Component`.
    """

    name: _t.Annotated[str, Field(pattern=r"^([a-zA-Z_][a-zA-Z0-9_-]*)$")]
    initial_values: _t.Annotated[dict[str, _t.Any], Field(default_factory=dict)]
    parameters: _t.Annotated[dict[str, _t.Any], Field(default_factory=dict)]
    constraints: _t.Annotated[dict[str, _t.Any], Field(default_factory=dict)]

    __pydantic_config__ = ConfigDict(extra="allow")


class ComponentSpec(PlugboardBaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
