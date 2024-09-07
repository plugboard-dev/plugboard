"""Provides `ComponentSpec` class."""

from pydantic import BaseModel


class ComponentSpec(BaseModel):
    """Specification of a Plugboard `Component`."""

    name: str
    type: str
    initial_values: dict
    parameters: dict
    constraints: dict
