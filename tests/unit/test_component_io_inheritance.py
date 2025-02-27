"""Tests `Component` `IOController` inheritance logic."""

from abc import ABC
from contextlib import nullcontext
import typing as _t

import pytest

from plugboard.component import IOController as IO
from plugboard.component.component import Component
from plugboard.events import Event
from plugboard.exceptions import IOSetupError


class EventType1(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_1"


class EventType2(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "event_2"


@pytest.mark.parametrize("io_args, exc", [({}, IOSetupError), ({"inputs": ["in_1", "in_2"]}, None)])
def test_io_inheritance(io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]]) -> None:
    """Tests that `Component` subclasses inherit `IOController` attributes."""
    with pytest.raises(exc) if exc is not None else nullcontext():

        class _A(Component):
            io: IO = IO(**io_args)

        for k in io_args:
            assert set(getattr(_A.io, k)) > set(getattr(Component.io, k))
        for k in {"inputs", "outputs", "input_events", "output_events"} - set(io_args.keys()):
            assert set(getattr(_A.io, k)) == set(getattr(Component.io, k))

    if exc is not None:
        return

    class _B(_A):
        io: IO = IO(
            inputs=["in_3"],
            outputs=["out_1"],
            input_events=[EventType1],
            output_events=[EventType2],
        )

    for k in {"inputs", "outputs", "input_events", "output_events"}:
        assert set(getattr(_B.io, k)) > set(getattr(_A.io, k))


@pytest.mark.parametrize("io_args, exc", [({}, None), ({"inputs": ["in_1", "in_2"]}, None)])
def test_io_inheritance_abc(io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]]) -> None:
    """Tests that abstract `Component` subclasses inherit `IOController` attributes."""
    with pytest.raises(exc) if exc is not None else nullcontext():

        class _A(Component, ABC):
            io: IO = IO(**io_args)

        for k in io_args:
            assert set(getattr(_A.io, k)) > set(getattr(Component.io, k))
        for k in {"inputs", "outputs", "input_events", "output_events"} - set(io_args.keys()):
            assert set(getattr(_A.io, k)) == set(getattr(Component.io, k))

    if exc is not None:
        return

    class _B(_A):
        io: IO = IO(
            inputs=["in_3"],
            outputs=["out_1"],
            input_events=[EventType1],
            output_events=[EventType2],
        )

    for k in {"inputs", "outputs", "input_events", "output_events"}:
        assert set(getattr(_B.io, k)) > set(getattr(_A.io, k))
