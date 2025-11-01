"""Unit tests for the component decorator."""
# ruff: noqa: D101,D102,D103

import asyncio

import pytest

from plugboard.component import Component, component


@component(inputs=["a"], outputs=["b"])
async def comp_b_func(a: int) -> dict[str, int]:
    """An example async function to be converted to a component."""
    await asyncio.sleep(0.01)
    return {"b": 2 * a}


@component(inputs=["a"], outputs=["c"])
def comp_c_func(a: int) -> dict[str, int]:
    """An example sync function to be converted to a component."""
    return {"c": 3 * a}


def test_component_decorator_creates_component_class_async_function() -> None:
    """Tests that the component decorator creates a component class correctly for async function."""
    comp_b = comp_b_func.component(name="comp_b")
    assert isinstance(comp_b, Component)
    assert comp_b.name == "comp_b"


def test_component_decorator_creates_component_class_sync_function() -> None:
    """Tests that the component decorator creates a component class correctly for sync function."""
    comp_c = comp_c_func.component(name="comp_c")
    assert isinstance(comp_c, Component)
    assert comp_c.name == "comp_c"


@pytest.mark.asyncio
async def test_component_decorator_call_async_function() -> None:
    """Tests that the component decorator calls the wrapped async function correctly."""
    result = await comp_b_func(5)
    assert result == {"b": 10}


@pytest.mark.asyncio
async def test_component_decorator_call_sync_function() -> None:
    """Tests that the component decorator calls the wrapped sync function correctly."""
    result = comp_c_func(5)
    assert result == {"c": 15}
