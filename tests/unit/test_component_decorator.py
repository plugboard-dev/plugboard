"""Unit tests for the component decorator."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.component import Component, component


@component(inputs=["a"], outputs=["b"])
async def comp_b_func(a: int) -> dict[str, int]:
    return {"b": 2 * a}


def test_component_decorator_creates_component_class() -> None:
    """Tests that the component decorator creates a component class correctly."""
    comp_b = comp_b_func.component(name="comp_b")
    assert isinstance(comp_b, Component)
    assert comp_b.name == "comp_b"


@pytest.mark.asyncio
async def test_component_decorator_calls_function() -> None:
    """Tests that the component decorator calls the wrapped function correctly."""
    result = await comp_b_func(5)
    assert result == {"b": 10}
