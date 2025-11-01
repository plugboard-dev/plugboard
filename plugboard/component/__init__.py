"""Component submodule providing functionality related to components and their execution."""

from plugboard.component.component import Component, ComponentRegistry
from plugboard.component.io_controller import IOController
from plugboard.component.utils import component


__all__ = [
    "component",
    "Component",
    "ComponentRegistry",
    "IOController",
]
