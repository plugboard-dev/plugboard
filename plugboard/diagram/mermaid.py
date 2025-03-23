"""Provides `MermaidDiagram` class for creating diagrams from `Process` objects."""

import typing as _t

from plugboard.component import Component
from plugboard.diagram import Diagram
from plugboard.events import Event
from plugboard.process import Process


class MermaidDiagram(Diagram):
    """`MermaidDiagram` class for creating diagrams of Plugboard processes using Mermaid."""

    _header: str = "flowchart LR\n"
    _component_shape: str = "rect"
    _event_shape: str = "hex"
    _component_connector: str = "-->"
    _event_connector: str = "-.->"

    def __init__(self, markdown: str) -> None:
        self._markdown = markdown

    def _node_from_component(self, component: Component) -> str:
        return (
            f"{component.id}@{{ shape: {self._component_shape}, label: "
            f"{component.__class__.__name__}<br>**{component.name}** }}"
        )

    def _node_from_event(self, event: Event) -> str:
        return f"{event.type}@{{ shape: {self._event_shape}, label: {event.__class__.__name__} }}"

    @property
    def diagram(self) -> str:
        """Returns a string representation of the diagram."""
        return self._markdown

    @classmethod
    def from_process(cls, process: Process, **kwargs: _t.Any) -> None:
        """Create the diagram.

        Args:
            process: The [`Process`][plugboard.process.Process] object to create the diagram from.
            **kwargs: Additional keyword arguments for the diagram backend.
        """
        pass
