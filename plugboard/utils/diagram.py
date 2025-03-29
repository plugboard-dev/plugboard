"""Utility functions for creating diagrams of Plugboard processes."""

from plugboard.diagram import MermaidDiagram
from plugboard.process import Process


def markdown_diagram(process: Process) -> str:
    """Returns a markdown representation of a [`Process`][plugboard.process.Process]."""
    diagram = MermaidDiagram.from_process(process).diagram
    return f"```mermaid\n{diagram}\n```"
