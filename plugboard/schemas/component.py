"""Provides `ComponentSpec` class."""

import typing as _t

from pydantic import BaseModel


class ComponentArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Optional; Initial values for the `Component`.
        parameters: Optional; Parameters for the `Component`.
        constraints: Optional; Constraints for the `Component`.
    """

    name: str
    initial_values: _t.Optional[dict] = None
    parameters: _t.Optional[dict] = None
    constraints: _t.Optional[dict] = None


class ComponentSpec(BaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
