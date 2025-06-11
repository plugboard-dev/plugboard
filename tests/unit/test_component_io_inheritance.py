"""Tests `Component` `IOController` inheritance logic."""

from abc import ABC
from contextlib import nullcontext
import typing as _t

import pytest
from ray.util.multiprocessing import Pool

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

            async def step(self) -> None:
                pass

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

        async def step(self) -> None:
            pass

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

        async def step(self) -> None:
            pass

    for k in {"inputs", "outputs", "input_events", "output_events"}:
        assert set(getattr(_B.io, k)) > set(getattr(_A.io, k))


@pytest.mark.parametrize("io_args, exc", [({"inputs": ["in_1", "in_2"]}, None)])
def test_io_inheritance_ray(
    io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]], ray_ctx: None
) -> None:
    """Tests that `Component` subclasses inherit `IOController` attributes when running on Ray."""

    def _test_io_inheritance_ray(
        io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]]
    ) -> None:
        import typing as _t

        from plugboard.component import IOController as IO

        class EventType1(Event):
            """An event type for testing."""

            type: _t.ClassVar[str] = "event_1"

        class EventType2(Event):
            """An event type for testing."""

            type: _t.ClassVar[str] = "event_2"

        with pytest.raises(exc) if exc is not None else nullcontext():

            class _A(Component):
                io: IO = IO(**io_args)

                async def step(self) -> None:
                    pass

            # On Ray, IO inheritance logic is applied at Component instantiation time until
            # https://github.com/ray-project/ray/issues/42823 is resolved
            a = _A(name="a")

            for k in io_args:
                assert set(getattr(a.io, k)) > set(getattr(Component.io, k))
            for k in {"inputs", "outputs", "input_events", "output_events"} - set(io_args.keys()):
                assert set(getattr(a.io, k)) == set(getattr(Component.io, k))

        if exc is not None:
            return

        class _B(_A):
            io: IO = IO(
                inputs=["in_3"],
                outputs=["out_1"],
                input_events=[EventType1],
                output_events=[EventType2],
            )

        b = _B(name="b")

        for k in {"inputs", "outputs", "input_events", "output_events"}:
            assert set(getattr(b.io, k)) > set(getattr(a.io, k))

    with Pool(1) as pool:
        pool.apply(_test_io_inheritance_ray, (io_args, exc))
