"""Component submodule providing functionality related to components and their execution."""

from plugboard.component.component import Component, ComponentRegistry
from plugboard.component.io_controller import IOController


__all__ = [
    "Component",
    "ComponentRegistry",
    "IOController",
]
