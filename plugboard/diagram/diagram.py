"""Provides `Diagram` base class for creating diagrams from `Process` objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
import typing as _t

from plugboard.process import Process


class Diagram(ABC):
    """`Diagram` base class for creating diagrams of Plugboard processes."""

    def __init__(self, **kwargs: _t.Any) -> None:
        """Instantiates `Diagram`."""
        pass

    @property
    @abstractmethod
    def diagram(self) -> str:
        """Returns a string representation of the diagram."""
        pass

    @classmethod
    @abstractmethod
    def from_process(cls, process: Process, **kwargs: _t.Any) -> Diagram:
        """Create the diagram.

        Args:
            process: The [`Process`][plugboard.process.Process] object to create the diagram from.
            **kwargs: Additional keyword arguments for the diagram backend.
        """
        pass

    def __str__(self) -> str:
        return self.diagram
