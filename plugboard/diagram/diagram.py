"""Provides `Diagram` base class for creating diagrams from `Process` objects."""

from abc import ABC, abstractmethod
import typing as _t

from plugboard.process import Process


class Diagram(ABC):
    """`Diagram` base class for creating diagrams of Plugboard processes."""

    @property
    @abstractmethod
    def diagram(self) -> str:
        """Returns a string representation of the diagram."""
        pass

    @classmethod
    @abstractmethod
    def from_process(cls, process: Process, **kwargs: _t.Any) -> None:
        """Create the diagram.

        Args:
            process: The [`Process`][plyboard.process.Process] object to create the diagram from.
            **kwargs: Additional keyword arguments for the diagram backend.
        """
        pass

    def __str__(self) -> str:
        return self.diagram
