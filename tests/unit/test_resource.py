"""Unit tests for Resource class."""
# ruff: noqa: D101,D102,D103

from pydantic import ValidationError
import pytest

from plugboard.schemas import Resource


def test_resource_default_values() -> None:
    """Test Resource default values."""
    resource = Resource()
    assert resource.cpu == 0.001
    assert resource.gpu == 0
    assert resource.memory == 0
    assert resource.resources == {}


def test_resource_numeric_values() -> None:
    """Test Resource with numeric values."""
    resource = Resource(cpu=2.5, gpu=1, memory=1024)
    assert resource.cpu == 2.5
    assert resource.gpu == 1.0
    assert resource.memory == 1024.0


def test_resource_string_milli_units() -> None:
    """Test Resource with milli-unit string values."""
    resource = Resource(cpu="250m", gpu="500m")
    assert resource.cpu == 0.25
    assert resource.gpu == 0.5


def test_resource_string_memory_units() -> None:
    """Test Resource with memory unit string values."""
    resource = Resource(memory="10Mi")
    assert resource.memory == 10 * 1024 * 1024

    resource = Resource(memory="5Gi")
    assert resource.memory == 5 * 1024 * 1024 * 1024

    resource = Resource(memory="2Ki")
    assert resource.memory == 2 * 1024

    resource = Resource(memory="1Ti")
    assert resource.memory == 1 * 1024 * 1024 * 1024 * 1024


def test_resource_string_plain_number() -> None:
    """Test Resource with plain number string values."""
    resource = Resource(cpu="2.5", gpu="1")
    assert resource.cpu == 2.5
    assert resource.gpu == 1.0


def test_resource_custom_resources() -> None:
    """Test Resource with custom resources dictionary."""
    resource = Resource(resources={"custom_gpu": 2, "special_hardware": "500m"})
    assert resource.resources == {"custom_gpu": 2.0, "special_hardware": 0.5}


def test_resource_invalid_milli_format() -> None:
    """Test Resource with invalid milli-unit format."""
    with pytest.raises(ValidationError):
        Resource(cpu="250x")


def test_resource_invalid_memory_format() -> None:
    """Test Resource with invalid memory format."""
    with pytest.raises(ValidationError):
        Resource(memory="10Xi")


def test_resource_invalid_string_format() -> None:
    """Test Resource with invalid string format."""
    with pytest.raises(ValidationError):
        Resource(cpu="invalid")


def test_resource_to_ray_options_default() -> None:
    """Test conversion to Ray options with default values."""
    resource = Resource()
    options = resource.to_ray_options()
    assert options == {"num_cpus": 0.001}


def test_resource_to_ray_options_all_fields() -> None:
    """Test conversion to Ray options with all fields set."""
    resource = Resource(cpu=2, gpu=1, memory=1024, resources={"custom": 5})
    options = resource.to_ray_options()
    assert options == {
        "num_cpus": 2.0,
        "num_gpus": 1.0,
        "memory": 1024.0,
        "resources": {"custom": 5.0},
    }


def test_resource_to_ray_options_only_cpu() -> None:
    """Test conversion to Ray options with only CPU."""
    resource = Resource(cpu="500m")
    options = resource.to_ray_options()
    assert options == {"num_cpus": 0.5}


def test_resource_to_ray_options_with_strings() -> None:
    """Test conversion to Ray options with string inputs."""
    resource = Resource(cpu="250m", memory="10Mi", resources={"custom": "100m"})
    options = resource.to_ray_options()
    assert options == {
        "num_cpus": 0.25,
        "memory": 10 * 1024 * 1024,
        "resources": {"custom": 0.1},
    }


def test_resource_to_ray_options_zero_values_excluded() -> None:
    """Test that zero values are excluded from Ray options (except CPU)."""
    resource = Resource(cpu=1, gpu=0, memory=0)
    options = resource.to_ray_options()
    assert options == {"num_cpus": 1.0}
    assert "num_gpus" not in options
    assert "memory" not in options
