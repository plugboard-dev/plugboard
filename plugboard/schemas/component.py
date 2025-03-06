"""Provides `ComponentSpec` class."""

import typing as _t

from pydantic import Field

from plugboard.schemas._common import PlugboardBaseModel


class ComponentArgsDict(_t.TypedDict):
    """`TypedDict` of the [`Component`][plugboard.component.Component] constructor arguments."""

    name: str
    initial_values: _t.NotRequired[dict[str, _t.Any] | None]
    parameters: _t.NotRequired[dict[str, _t.Any] | None]
    constraints: _t.NotRequired[dict[str, _t.Any] | None]


class ComponentArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Initial values for the `Component`.
        parameters: Parameters for the `Component`.
        constraints: Constraints for the `Component`.
    """

    name: str = Field(pattern=r"^([a-zA-Z_][a-zA-Z0-9_-]*)$")
    initial_values: dict[str, _t.Any] = {}
    parameters: dict[str, _t.Any] = {}
    constraints: dict[str, _t.Any] = {}


class ComponentSpec(PlugboardBaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
