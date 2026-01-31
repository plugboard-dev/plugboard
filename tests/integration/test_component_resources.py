"""Integration tests for Components with resource requirements."""
# ruff: noqa: D101,D102,D103

import typing as _t

import pytest

from plugboard.component import Component, IOController as IO
from plugboard.process import LocalProcess
from plugboard.schemas import Resource


class ResourceComponent(Component):
    """Test component with resource requirements."""

    io = IO(inputs=["a"], outputs=["b"])

    def __init__(self, multiplier: int = 1, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._multiplier = multiplier

    async def step(self) -> None:
        if self.a is not None:
            self.b = self.a * self._multiplier
        await self.io.close()


@pytest.mark.asyncio
async def test_component_with_resources() -> None:
    """Test that a component can be created with resource requirements."""
    resources = Resource(cpu="500m", gpu=1, memory="10Mi")
    component = ResourceComponent(name="test", resources=resources)

    assert component.resources == resources
    assert component.resources.cpu == 0.5
    assert component.resources.gpu == 1.0
    assert component.resources.memory == 10 * 1024 * 1024


@pytest.mark.asyncio
async def test_component_with_default_resources() -> None:
    """Test that a component uses default resources when none specified."""
    component = ResourceComponent(name="test")

    assert component.resources is None


@pytest.mark.asyncio
async def test_component_resources_in_local_process() -> None:
    """Test that components with resources work in LocalProcess."""
    resources = Resource(cpu=1.0, memory="100Mi")
    component = ResourceComponent(
        name="test",
        resources=resources,
        multiplier=2,
        initial_values={"a": [5]},
    )

    process = LocalProcess(components=[component], connectors=[])

    async with process:
        await process.run()

    assert component.b == 10
    assert component.resources.cpu == 1.0


@pytest.mark.asyncio
async def test_component_export_includes_resources() -> None:
    """Test that component export includes resource requirements."""
    resources = Resource(cpu="250m", gpu=0.5, memory="5Gi")
    component = ResourceComponent(name="test", resources=resources)

    exported = component.export()
    assert "args" in exported
    # The resources should be passed through in the exported args
    assert exported["args"]["resources"] == resources
