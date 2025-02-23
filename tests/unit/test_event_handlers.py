"""Provides tests for event handlers class."""

from collections import defaultdict
from contextlib import nullcontext
import typing as _t

import pytest

from plugboard.component import Component, IOController
from plugboard.events import Event, EventHandlers


class A(Component):
    """A test component."""

    io: IOController = IOController(outputs=["out_1"])

    async def step(self) -> None:
        """A test step."""
        pass

    async def event_1_handler(self) -> None:
        """A test event handler for event type 1."""
        pass

    async def event_2_handler(self) -> None:
        """A test event handler for event type 2."""
        pass


class EventType1(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_1"


class EventType2(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_2"


@pytest.fixture(scope="function", autouse=True)
def reset_event_handlers() -> None:
    """Resets the event handlers after each test."""
    EventHandlers._handlers = defaultdict(dict)


def test_component_event_handlers_add() -> None:
    """Tests that the `add` decorator registers component event handlers."""
    setattr(A, "event_1_handler", EventHandlers.add(EventType1)(A.event_1_handler))
    assert EventHandlers._handlers == {
        f"{A.__module__}.{A.__name__}": {EventType1.type: A.event_1_handler}
    }
    assert A.event_1_handler.__name__ == "event_1_handler"


@pytest.mark.parametrize(
    "queried_class,event_type,expected_handler,exception_context",
    [
        (A, EventType1, A.event_1_handler, nullcontext()),
        (A, EventType2, None, pytest.raises(KeyError)),
        (int, EventType1, None, pytest.raises(KeyError)),
    ],
)
def test_component_event_handlers_get(
    queried_class: _t.Type,
    event_type: _t.Type[Event],
    expected_handler: _t.Callable,
    exception_context: _t.ContextManager,
) -> None:
    """Tests that the `get` method retrieves component event handlers."""
    setattr(A, "event_1_handler", EventHandlers.add(EventType1)(A.event_1_handler))
    with exception_context:
        assert EventHandlers.get(queried_class, event_type) == expected_handler
