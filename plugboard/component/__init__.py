"""Component submodule providing functionality related to components and their execution."""

from plugboard.component.component import Component
from plugboard.component.io_controller import IOController, IOStreamClosedError


__all__ = [
    "Component",
    "IOController",
    "IOStreamClosedError",
]
