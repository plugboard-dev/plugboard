"""Unit tests for the diagram classes."""
# ruff: noqa: D101,D102,D103

import re
import typing as _t
from urllib.parse import quote_plus

import pytest

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector, ConnectorBuilder
from plugboard.diagram import MermaidDiagram
from plugboard.events import Event, EventConnectorBuilder
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec


MERMAID_REGEX = (
    r"^([\w-]+)@\{ shape: (rounded|hex), label: (.*?) \} (-->|-\.->) "
    r"([\w-]+)@\{ shape: (rounded|hex), label: (.*?) \}$"
)


class EventX(Event):
    type: _t.ClassVar[str] = "EventX"


class EventY(Event):
    type: _t.ClassVar[str] = "EventY"


class A(Component):
    """A simple component for testing."""

    io = IO(inputs=["a", "b"], outputs=["c"])

    async def step(self) -> None:
        pass


class B(Component):
    """A simple component for testing."""

    io = IO(inputs=["c"], input_events=[EventX], output_events=[EventY])

    async def step(self) -> None:
        pass


class C(Component):
    """A simple component for testing."""

    io = IO(input_events=[EventY])

    async def step(self) -> None:
        pass


@pytest.fixture
def process() -> LocalProcess:
    """Fixture for a `Process` object."""
    components = [A(name="component-a"), B(name="component-b"), C(name="component-c")]
    connectors = [
        AsyncioConnector(spec=ConnectorSpec(source="component-a.c", target="component-b.c")),
        AsyncioConnector(spec=ConnectorSpec(source="component-b.c", target="component-c.c")),
    ]
    connector_builder = ConnectorBuilder(connector_cls=AsyncioConnector)  # (2)!
    event_connector_builder = EventConnectorBuilder(connector_builder=connector_builder)
    event_connectors = list(event_connector_builder.build(components).values())
    return LocalProcess(components=components, connectors=connectors + event_connectors)


def test_mermaid_diagram(process: LocalProcess) -> None:
    """Test generation of mermaid diagrams."""
    diagram = MermaidDiagram.from_process(process)

    diagram_string = diagram.diagram

    # Must contain a row for each connector plus the header
    rows = diagram_string.split("\n")
    assert len(rows) == len(process.connectors) + 1
    # Rows must match the expected format
    for row in rows[1:]:
        assert re.match(MERMAID_REGEX, row.strip())
    # URL must be valid
    assert diagram.url.startswith("https://mermaid.live/edit#pako:")
    # Pako must be URL-encoded to ensure compatibility with https://mermaid.ink
    pako_str = diagram.url.split("pako:")[-1]
    assert quote_plus(pako_str) == pako_str
    # String representation must match the diagram
    assert str(diagram) == diagram_string
