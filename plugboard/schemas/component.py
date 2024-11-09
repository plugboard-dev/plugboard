"""Provides `ComponentSpec` class."""

from pydantic import Field

from plugboard.schemas._common import PlugboardBaseModel


class ComponentArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Initial values for the `Component`.
        parameters: Parameters for the `Component`.
        constraints: Constraints for the `Component`.
    """

    name: str = Field(pattern=r"^([a-zA-Z_][a-zA-Z0-9_-]*)$")
    initial_values: dict = {}
    parameters: dict = {}
    constraints: dict = {}


class ComponentSpec(PlugboardBaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
