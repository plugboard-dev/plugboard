"""Integration test for event handlers in a component."""

import asyncio
import typing as _t

from pydantic import BaseModel
import pytest
import pytest_asyncio
import pytest_cases

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioConnector, Connector, ConnectorBuilder
from plugboard.events import Event, EventConnectorBuilder
from plugboard.schemas import ConnectorSpec
from tests.conftest import zmq_connector_cls


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


@pytest_cases.fixture(scope="function")
@pytest_cases.parametrize("_connector_cls", [AsyncioConnector, zmq_connector_cls])
def connector_cls(_connector_cls: _t.Type[Connector]) -> _t.Type[Connector]:
    """Returns a `Connector` class."""
    return _connector_cls


@pytest.fixture
def event_connectors(connector_cls: _t.Type[Connector]) -> EventConnectorBuilder:
    """Fixture for an event connectors instance."""
    connector_builder = ConnectorBuilder(connector_cls=connector_cls)
    return EventConnectorBuilder(connector_builder=connector_builder)


@pytest.mark.asyncio
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

    await a.io.connect(connectors)

    assert a.event_A_count == 0
    assert a.event_B_count == 0

    evt_A = EventTypeA(data=EventTypeAData(x=2), source="test-driver")
    chan_A = await event_connectors_map[evt_A.type].connect_send()
    await chan_A.send(evt_A)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 0

    evt_B = EventTypeB(data=EventTypeBData(y=4), source="test-driver")
    chan_B = await event_connectors_map[evt_B.type].connect_send()
    await chan_B.send(evt_B)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4

    await a.io.close()


@pytest_asyncio.fixture
async def field_connectors(connector_cls: _t.Type[Connector]) -> list[Connector]:
    """Fixture for a list of field connectors."""
    return [
        connector_cls(spec=ConnectorSpec(source="null.in_1", target="a.in_1")),
        connector_cls(spec=ConnectorSpec(source="null.in_2", target="a.in_2")),
        connector_cls(spec=ConnectorSpec(source="a.out_1", target="null.out_1")),
    ]


@pytest.mark.asyncio
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

    # FIXME : With `ZMQConnector` both send and recv side must be connected to avoid hanging.
    #       : See https://github.com/plugboard-dev/plugboard/issues/101.
    conn_in1, conn_in2, conn_out1 = field_connectors
    async with asyncio.TaskGroup() as tg:
        tg.create_task(a.io.connect(connectors))
        t_in1 = tg.create_task(conn_in1.connect_send())
        t_in2 = tg.create_task(conn_in2.connect_send())
        tg.create_task(conn_out1.connect_recv())
    chan_in1, chan_in2 = t_in1.result(), t_in2.result()

    # Initially event counters should be zero
    assert a.event_A_count == 0
    assert a.event_B_count == 0
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending one event of type A, the event_A_count should be 2
    evt_A = EventTypeA(data=EventTypeAData(x=2), source="test-driver")
    chan_A = await event_connectors_map[evt_A.type].connect_send()
    await chan_A.send(evt_A)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 0
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending one event of type B, the event_B_count should be 4
    evt_B = EventTypeB(data=EventTypeBData(y=4), source="test-driver")
    chan_B = await event_connectors_map[evt_B.type].connect_send()
    await chan_B.send(evt_B)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) is None
    assert getattr(a, "in_2", None) is None

    # After sending data for input fields, the event counters should remain the same
    await chan_in1.send(1)
    await chan_in2.send(2)
    await a.step()

    assert a.event_A_count == 2
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 1
    assert getattr(a, "in_2", None) == 2

    # After sending data for only one input field, step should timeout as read tasks are incomplete
    await chan_in1.send(3)
    step_task = asyncio.create_task(a.step())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(step_task), timeout=0.1)

    # After sending an event of type A before all field data is sent, the event_A_count should be 4
    await chan_A.send(evt_A)
    await step_task

    assert a.event_A_count == 4
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 1
    assert getattr(a, "in_2", None) == 2

    # After sending data for the other input field, the event counters should remain the same
    await chan_in2.send(4)
    await a.step()

    assert a.event_A_count == 4
    assert a.event_B_count == 4
    assert getattr(a, "in_1", None) == 3
    assert getattr(a, "in_2", None) == 4

    # After sending data for both input fields and both events, the event counters should
    # eventually be updated after at most two steps
    await chan_in1.send(5)
    await chan_in2.send(6)
    await chan_A.send(evt_A)
    await chan_B.send(evt_B)
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
