"""Provides `MermaidDiagram` class for creating diagrams from `Process` objects."""

from __future__ import annotations

import base64
import typing as _t
import zlib

from msgspec import json

from plugboard.component import Component
from plugboard.diagram import Diagram
from plugboard.events import Event
from plugboard.process import Process


MERMAIDLIVE_URL = "https://mermaid.live/edit"


def _pako_deflate(data: bytes) -> bytes:
    """Creates data string for the Mermaid service.

    See https://github.com/nodeca/pako
    """
    compress = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY)
    try:
        compressed_data = compress.compress(data)
        compressed_data += compress.flush()
    except zlib.error as e:
        raise ValueError(f"Zlib compression failed: {e}") from e
    return compressed_data


class MermaidDiagram(Diagram):
    """`MermaidDiagram` class for creating diagrams of Plugboard processes using Mermaid."""

    _header: str = "flowchart LR"
    _component_shape: str = "rounded"
    _event_shape: str = "hex"
    _component_connector: str = "-->"
    _event_connector: str = "-.->"

    def __init__(self, spec: str) -> None:
        """Instantiates `MermaidDiagram`.

        Args:
            spec: The string representation of the diagram.
        """
        self._spec = spec

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
        return self._spec

    @property
    def url(self) -> str:
        """Returns a URL to the diagram on [Mermaid Live Editor](https://mermaid.live/)."""
        json_bytes = json.encode({"code": self._spec, "mermaid": {"theme": "default"}})
        b64_pako = base64.urlsafe_b64encode(_pako_deflate(json_bytes))
        return f"{MERMAIDLIVE_URL}#pako:{b64_pako.decode('utf-8')}"

    @classmethod
    def from_process(cls, process: Process, **kwargs: _t.Any) -> MermaidDiagram:
        """Create the diagram.

        Args:
            process: The [`Process`][plugboard.process.Process] object to create the diagram from.
            **kwargs: Additional keyword arguments for the diagram backend.
        """
        lines = []
        for source, target in cls._source_target_connections(process):
            lines.append(
                f"{cls._node_from_component(source)} "
                f"{cls._component_connector} "
                f"{cls._node_from_component(target)}"
            )
        for event, component in cls._event_inputs(process):
            lines.append(
                f"{cls._node_from_event(event)} "
                f"{cls._event_connector} "
                f"{cls._node_from_component(component)}"
            )
        for event, component in cls._event_outputs(process):
            lines.append(
                f"{cls._node_from_component(component)} "
                f"{cls._event_connector} "
                f"{cls._node_from_event(event)}"
            )
        return cls(spec="\n  ".join((cls._header, *lines)), **kwargs)
