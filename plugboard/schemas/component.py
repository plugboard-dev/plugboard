"""Provides `ComponentSpec` class."""

import typing as _t

from pydantic import BaseModel


class ComponentArgsSpec(BaseModel, extra="allow"):
    """Specification of the `Component` constructor arguments."""

    name: str
    initial_values: _t.Optional[dict] = None
    parameters: _t.Optional[dict] = None
    constraints: _t.Optional[dict] = None


class ComponentSpec(BaseModel):
    """Specification of a Plugboard `Component`."""

    name: str
    args: ComponentArgsSpec
