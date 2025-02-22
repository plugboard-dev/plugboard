"""Tests `Component` `IOController` inheritance logic."""

from abc import ABC
from contextlib import nullcontext
import typing as _t

import pytest

from plugboard.component import IOController as IO
from plugboard.component.component import Component


@pytest.mark.parametrize("io_args, exc", [({}, ValueError), ({"inputs": ["in_1", "in_2"]}, None)])
def test_io_inheritance(io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]]) -> None:
    """Tests that `Component` subclasses inherit `IOController` attributes."""
    with pytest.raises(exc) if exc else nullcontext():

        class _A(Component):
            io: IO = IO(**io_args)

        for k in io_args:
            assert set(getattr(_A.io, k)) > set(getattr(Component.io, k))
        for k in {"inputs", "outputs", "input_events", "output_events"} - set(io_args.keys()):
            assert set(getattr(_A.io, k)) == set(getattr(Component.io, k))


@pytest.mark.parametrize("io_args, exc", [({}, None), ({"inputs": ["in_1", "in_2"]}, None)])
def test_io_inheritance_abc(io_args: dict[str, _t.Any], exc: _t.Optional[type[Exception]]) -> None:
    """Tests that abstract `Component` subclasses inherit `IOController` attributes."""
    with pytest.raises(exc) if exc else nullcontext():

        class _A(Component, ABC):
            io: IO = IO(**io_args)

        for k in io_args:
            assert set(getattr(_A.io, k)) > set(getattr(Component.io, k))
        for k in {"inputs", "outputs", "input_events", "output_events"} - set(io_args.keys()):
            assert set(getattr(_A.io, k)) == set(getattr(Component.io, k))
