"""Provides `MermaidDiagram` class for creating diagrams from `Process` objects."""

from __future__ import annotations

import typing as _t

from plugboard.component import Component
from plugboard.diagram import Diagram
from plugboard.events import Event
from plugboard.process import Process


class MermaidDiagram(Diagram):
    """`MermaidDiagram` class for creating diagrams of Plugboard processes using Mermaid."""

    _header: str = "flowchart LR"
    _component_shape: str = "rect"
    _event_shape: str = "hex"
    _component_connector: str = "-->"
    _event_connector: str = "-.->"

    def __init__(self, markdown: str) -> None:
        self._markdown = markdown

    @classmethod
    def _node_from_component(cls, component: Component) -> str:
        return (
            f"{component.id}@{{ shape: {cls._component_shape}, label: "
            f"{component.__class__.__name__}<br>**{component.name}** }}"
        )

    @classmethod
    def _node_from_event(cls, event: _t.Type[Event]) -> str:
        return f"{event.type}@{{ shape: {cls._event_shape}, label: {event.__name__} }}"

    @property
    def diagram(self) -> str:
        """Returns a string representation of the diagram."""
        return self._markdown

    @classmethod
    def from_process(cls, process: Process, **kwargs: _t.Any) -> MermaidDiagram:
        """Create the diagram.

        Args:
            process: The [`Process`][plugboard.process.Process] object to create the diagram from.
            **kwargs: Additional keyword arguments for the diagram backend.
        """
        lines = []
        for connector in process.connectors.values():
            connector_spec = connector.spec
            try:
                source = process.components[connector_spec.source.entity]
                target = process.components[connector_spec.target.entity]
            except KeyError:
                # Skip event connectors here
                continue
            lines.append(
                f"{cls._node_from_component(source)} "
                f"{cls._component_connector} "
                f"{cls._node_from_component(target)}"
            )
        for component in process.components.values():
            for event in component.io.input_events:
                if event.__name__ == "StopEvent":
                    continue
                lines.append(
                    f"{cls._node_from_event(event)} "
                    f"{cls._event_connector} "
                    f"{cls._node_from_component(component)}"
                )
            for event in component.io.output_events:
                if event.__name__ == "StopEvent":
                    continue
                lines.append(
                    f"{cls._node_from_component(component)} "
                    f"{cls._event_connector} "
                    f"{cls._node_from_event(event)}"
                )
        return cls(markdown=f"{cls._header}\n" + "\n".join(f"  {x}" for x in lines), **kwargs)
