"""Provides `ComponentSpec` class."""

import typing as _t

from pydantic import ConfigDict, Field, with_config

from plugboard.schemas._common import PlugboardBaseModel


@with_config(ConfigDict(extra="allow"))
class ComponentArgsSpec(_t.TypedDict):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Optional; initial values for the `Component`.
        parameters: Optional; parameters for the `Component`.
        constraints: Optional; constraints for the `Component`.
    """

    name: _t.Annotated[str, Field(pattern=r"^([a-zA-Z_][a-zA-Z0-9_-]*)$")]
    initial_values: _t.Annotated[_t.Optional[dict[str, _t.Any] | None], Field(default=None)]
    parameters: _t.Annotated[_t.Optional[dict[str, _t.Any]], Field(default=None)]
    constraints: _t.Annotated[_t.Optional[dict[str, _t.Any]], Field(default=None)]


class ComponentSpec(PlugboardBaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
