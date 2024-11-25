"""Integration test for event handlers in a component."""

import asyncio
import typing as _t

from pydantic import BaseModel
import pytest

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioChannel, AsyncioChannelBuilder, ChannelBuilder, Connector
from plugboard.events import Event, EventConnectorBuilder
from plugboard.schemas import ConnectorSpec


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

    @EventTypeA.handler
    async def event_A_handler(self, evt: EventTypeA) -> None:
        """A test event handler."""
        self._event_A_count += evt.data.x

    @EventTypeB.handler
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
@pytest.mark.parametrize(
    "io_controller_kwargs",
    [
        {
            "inputs": [],
            "outputs": [],
            "input_events": [EventTypeA, EventTypeB],
            "output_events": [],
        },
        {
            "inputs": ["in_1"],
            "outputs": ["out_1"],
            "input_events": [EventTypeA, EventTypeB],
            "output_events": [],
        },
        {
            "inputs": ["in_1", "in_2"],
            "outputs": ["out_1"],
            "input_events": [EventTypeA, EventTypeB],
            "output_events": [],
        },
    ],
)
async def test_component_event_handlers(
    io_controller_kwargs: dict, event_connectors: EventConnectorBuilder
) -> None:
    """Test that event handlers are registered and called correctly for components."""

    class _A(A):
        io = IOController(**io_controller_kwargs)

    a = _A(name="a")

    event_connectors_map = event_connectors.build([a])
    connectors = list(event_connectors_map.values())

    a.io.connect(connectors)

    assert a.event_A_count == 0
    assert a.event_B_count == 0

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


@pytest.fixture
def field_connectors() -> list[Connector]:
    """Fixture for a list of field connectors."""
    return [
        Connector(
            spec=ConnectorSpec(source="null.in_1", target="a.in_1"),
            channel=AsyncioChannel(),
        ),
        Connector(
            spec=ConnectorSpec(source="null.in_2", target="a.in_2"),
            channel=AsyncioChannel(),
        ),
        Connector(
            spec=ConnectorSpec(source="a.out_1", target="null.out_1"),
            channel=AsyncioChannel(),
        ),
    ]


@pytest.mark.anyio
async def test_component_event_handlers_with_field_inputs(
    event_connectors: EventConnectorBuilder,
    field_connectors: list[Connector],
) -> None:
    """Test that event handlers are registered and called correctly for components."""

    class _A(A):
        io = IOController(
            inputs=["in_1", "in_2"],
            outputs=["out_1"],
            input_events=[EventTypeA, EventTypeB],
            output_events=[],
        )

    a = _A(name="a")

    event_connectors_map = event_connectors.build([a])
    connectors = list(event_connectors_map.values()) + field_connectors

    a.io.connect(connectors)

    # Initially event counters should be zero
    assert a.event_A_count == 0
    assert a.event_B_count == 0
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending one event of type A, the event_A_count should be 2
    evt_A = EventTypeA(data=EventTypeAData(x=2), source="test-driver")
    await event_connectors_map[evt_A.type].channel.send(evt_A)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 0
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending one event of type B, the event_B_count should be 4
    evt_B = EventTypeB(data=EventTypeBData(y=4), source="test-driver")
    await event_connectors_map[evt_B.type].channel.send(evt_B)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending data for input fields, the event counters should remain the same
    await field_connectors[0].channel.send(1)
    await field_connectors[1].channel.send(2)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 1
    assert getattr(a, "in_2", None) == 2

    # After sending data for only one input field, step should timeout as read tasks are incomplete
    await field_connectors[0].channel.send(3)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(a.step(), timeout=0.1)

    # After sending an event of type A before all field data is sent, the event_A_count should be 4
    await event_connectors_map[evt_A.type].channel.send(evt_A)
    await a.step()

    assert a.event_A_count == 4
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 1
    assert getattr(a, "in_2", None) == 2

    # After sending data for the other input field, the event counters should remain the same
    await field_connectors[1].channel.send(4)
    await a.step()

    assert a.event_A_count == 4
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 3
    assert getattr(a, "in_2", None) == 4

    # After sending data for both input fields and both events, the event counters should
    # eventually be updated after at most two steps
    await field_connectors[0].channel.send(5)
    await field_connectors[1].channel.send(6)
    await event_connectors_map[evt_A.type].channel.send(evt_A)
    await event_connectors_map[evt_B.type].channel.send(evt_B)
    await a.step()
    try:
        # All read tasks may have completed in a single step, so timeout rather than wait forever
        await asyncio.wait_for(a.step(), timeout=0.1)
    except asyncio.TimeoutError:
        pass

    assert a.event_A_count == 6
    assert a.event_B_count == 8
    assert getattr(a, "in_1", None) == 5
    assert getattr(a, "in_2", None) == 6

    await a.io.close()
