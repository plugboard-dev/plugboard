"""Integration test for event handlers in a component."""

import typing as _t

from pydantic import BaseModel
import pytest

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioChannelBuilder, ChannelBuilder
from plugboard.events import Event, EventConnectorBuilder, EventHandlers


class EventTypeAData(BaseModel):
    """Data for event_A."""

    x: int


class EventTypeA(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_A"
    data: EventTypeAData


class EventTypeBData(BaseModel):
    """Data for event_B."""

    y: int


class EventTypeB(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_B"
    data: EventTypeBData


class A(Component):
    """A test component."""

    io = IOController(input_events=[EventTypeA, EventTypeB])

    def __init__(self: _t.Self, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._event_A_count: int = 0
        self._event_B_count: int = 0

    @property
    def event_A_count(self) -> int:
        """Number of times event_A has been handled."""
        return self._event_A_count

    @property
    def event_B_count(self) -> int:
        """Number of times event_B has been handled."""
        return self._event_B_count

    async def step(self) -> None:
        """A test step."""
        pass

    @EventHandlers.add(EventTypeA)
    async def event_A_handler(self, evt: EventTypeA) -> None:
        """A test event handler."""
        self._event_A_count += evt.data.x

    @EventHandlers.add(EventTypeB)
    async def event_B_handler(self, evt: EventTypeB) -> None:
        """A test event handler."""
        self._event_B_count += evt.data.y


@pytest.fixture
def channel_builder() -> ChannelBuilder:
    """Fixture for an asyncio channel builder."""
    return AsyncioChannelBuilder()


@pytest.fixture
def event_connectors(channel_builder: ChannelBuilder) -> EventConnectorBuilder:
    """Fixture for an event connectors instance."""
    return EventConnectorBuilder(channel_builder=channel_builder)


@pytest.mark.anyio
async def test_component_event_handlers(event_connectors: EventConnectorBuilder) -> None:
    """Test that event handlers are registered and called correctly for components."""
    a = A(name="a")

    assert a.event_A_count == 0
    assert a.event_B_count == 0

    event_connectors_map = event_connectors.build([a])
    connectors = list(event_connectors_map.values())

    a.io.connect(connectors)

    evt_A = EventTypeA(data=EventTypeAData(x=2), source="test-driver")
    await event_connectors_map[evt_A.type].channel.send(evt_A)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 0

    evt_B = EventTypeB(data=EventTypeBData(y=4), source="test-driver")
    await event_connectors_map[evt_B.type].channel.send(evt_B)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4

    await a.io.close()
