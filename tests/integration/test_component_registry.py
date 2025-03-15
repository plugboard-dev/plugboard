"""Integration tests for the `ComponentRegistry`."""

import inspect

from plugboard import library
from plugboard.component import Component, ComponentRegistry


def test_component_registry() -> None:
    """Tests that all library components are registered."""
    library_components = [
        cls
        for cls in library.__dict__.values()
        if inspect.isclass(cls) and issubclass(cls, Component)
    ]
    # All classes must be in registry
    for cls in library_components:
        assert ComponentRegistry.get(cls.__name__) == cls
