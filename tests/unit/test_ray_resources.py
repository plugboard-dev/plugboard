"""Unit tests for RayProcess resource handling."""
# ruff: noqa: D101,D102,D103

from plugboard.component import Component, IOController as IO
from plugboard.schemas import Resource


class SimpleComponent(Component):
    """Simple test component."""

    io = IO(inputs=["a"], outputs=["b"])


def test_component_with_resources_to_ray_options() -> None:
    """Test that component resources are correctly converted to Ray options."""
    resources = Resource(cpu="500m", gpu=1, memory="10Mi", resources={"custom_gpu": 2})

    component = SimpleComponent(name="test", resources=resources)

    # Verify resources are stored
    assert component.resources is not None
    assert component.resources.cpu == 0.5
    assert component.resources.gpu == 1.0
    assert component.resources.memory == 10 * 1024 * 1024
    assert component.resources.resources == {"custom_gpu": 2.0}

    # Verify Ray options conversion
    ray_options = component.resources.to_ray_options()
    assert ray_options == {
        "num_cpus": 0.5,
        "num_gpus": 1.0,
        "memory": 10485760.0,
        "resources": {"custom_gpu": 2.0},
    }


def test_component_default_resources_to_ray_options() -> None:
    """Test that default resources are correctly converted to Ray options."""
    # Component without resources should use defaults when creating Ray options
    default_resources = Resource()

    ray_options = default_resources.to_ray_options()
    assert ray_options == {"num_cpus": 0.001}
    assert "num_gpus" not in ray_options
    assert "memory" not in ray_options


def test_component_with_zero_resources() -> None:
    """Test that zero resources are handled correctly."""
    resources = Resource(cpu=0, gpu=0, memory=0)

    component = SimpleComponent(name="test", resources=resources)

    # Zero values should be stored
    assert component.resources.cpu == 0
    assert component.resources.gpu == 0
    assert component.resources.memory == 0

    # But excluded from Ray options
    ray_options = component.resources.to_ray_options()
    assert ray_options == {}
