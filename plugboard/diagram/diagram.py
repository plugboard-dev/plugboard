"""Provides `Diagram` base class for creating diagrams from `Process` objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
import typing as _t

from plugboard.component import Component
from plugboard.events import Event, SystemEvent
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

    @classmethod
    def _source_target_connections(
        cls, process: Process
    ) -> _t.Iterator[tuple[Component, Component]]:
        """Yields source-target component tuples."""
        for connector in process.connectors.values():
            connector_spec = connector.spec
            try:
                source = process.components[connector_spec.source.entity]
                target = process.components[connector_spec.target.entity]
            except KeyError:
                # Skip event connectors here
                continue
            yield (source, target)

    @classmethod
    def _event_inputs(cls, process: Process) -> _t.Iterator[tuple[type[Event], Component]]:
        """Yields event, component tuples."""
        for component in process.components.values():
            for event in component.io.input_events:
                if issubclass(event, SystemEvent):
                    continue
                yield (event, component)

    @classmethod
    def _event_outputs(cls, process: Process) -> _t.Iterator[tuple[type[Event], Component]]:
        """Yields event, component tuples."""
        for component in process.components.values():
            for event in component.io.output_events:
                if issubclass(event, SystemEvent):
                    continue
                yield (event, component)
