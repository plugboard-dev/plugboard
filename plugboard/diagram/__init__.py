"""Provides classes and helper functions to visualise Plugboard processes."""

from plugboard.diagram.diagram import Diagram
from plugboard.diagram.mermaid import MermaidDiagram
from plugboard.process import Process


def markdown_diagram(process: Process) -> str:
    """Returns a markdown representation of a [`Process`][plugboard.process.Process]."""
    diagram = MermaidDiagram.from_process(process).diagram
    return f"```mermaid\n{diagram}\n```"


__all__ = ["Diagram", "MermaidDiagram", "markdown_diagram"]
