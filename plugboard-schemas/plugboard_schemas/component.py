"""Provides `ComponentSpec` class."""

import re
import typing as _t

from pydantic import Field, field_validator

from ._common import PlugboardBaseModel


RESOURCE_SUFFIXES = {
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
    "E": 1e18,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
}


def _parse_resource_value(value: str | float | int) -> float:
    """Parse a resource value from string or number.

    Supports:
    - Direct numerical values: 1, 0.5, 2.0
    - Decimal SI prefixes: n, u, m, k, M, G, T, P, E (e.g., "250m" -> 0.25, "5k" -> 5000)
    - Binary prefixes: Ki, Mi, Gi, Ti, Pi, Ei (e.g., "10Mi" -> 10485760)

    Args:
        value: The resource value to parse.

    Returns:
        The parsed float value.

    Raises:
        ValueError: If the value format is invalid.
    """
    if isinstance(value, (int, float)):
        return float(value)

    # Handle string values
    value = value.strip()

    # Sort by length (longest first) to match "Ki" before "k", etc.
    for suffix in sorted(RESOURCE_SUFFIXES.keys(), key=len, reverse=True):
        if value.endswith(suffix):
            # Use re.escape to safely escape the suffix in the regex pattern
            pattern = rf"^(\d+(?:\.\d+)?){re.escape(suffix)}$"
            match = re.match(pattern, value)
            if match:
                return float(match.group(1)) * RESOURCE_SUFFIXES[suffix]
            raise ValueError(f"Invalid format for suffix '{suffix}': {value}")

    # Try to parse as a plain number
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid resource value format: {value}")


class Resource(PlugboardBaseModel):
    """Resource requirements for a component.

    Supports specification of CPU, GPU, memory, and custom resources.
    Values can be specified as numbers or strings with units (e.g., "250m" for 0.25, "10Mi" for
    10 * 1024 * 1024).

    Attributes:
        cpu: CPU requirement (default: 0.001).
        gpu: GPU requirement (default: 0).
        memory: Memory requirement in bytes as an integer (default: 0).
        resources: Custom resource requirements as a dictionary.
    """

    cpu: float = 0.001
    gpu: float = 0
    memory: int = 0
    resources: dict[str, float] = Field(default_factory=dict)

    @field_validator("cpu", "gpu", mode="before")
    @classmethod
    def _parse_cpu_gpu_field(cls, v: str | float | int) -> float:
        """Validate and parse CPU and GPU fields."""
        return _parse_resource_value(v)

    @field_validator("memory", mode="before")
    @classmethod
    def _parse_memory_field(cls, v: str | float | int) -> int:
        """Validate and parse memory field as integer bytes."""
        return int(_parse_resource_value(v))

    @field_validator("resources", mode="before")
    @classmethod
    def _parse_resources_dict(cls, v: dict[str, str | float | int]) -> dict[str, float]:
        """Validate and parse custom resources dictionary."""
        return {key: _parse_resource_value(value) for key, value in v.items()}

    def to_ray_options(self) -> dict[str, _t.Any]:
        """Convert resource requirements to Ray actor options.

        Returns:
            Dictionary of Ray actor options.
        """
        options: dict[str, _t.Any] = {}

        if self.cpu > 0:
            options["num_cpus"] = self.cpu
        if self.gpu > 0:
            options["num_gpus"] = self.gpu
        if self.memory > 0:
            options["memory"] = self.memory

        # Add custom resources
        if self.resources:
            options["resources"] = self.resources

        return options


class ComponentArgsDict(_t.TypedDict):
    """`TypedDict` of the [`Component`][plugboard.component.Component] constructor arguments."""

    name: str
    initial_values: _t.NotRequired[dict[str, _t.Any] | None]
    parameters: _t.NotRequired[dict[str, _t.Any] | None]
    constraints: _t.NotRequired[dict[str, _t.Any] | None]
    resources: _t.NotRequired[Resource | None]


class ComponentArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`Component`][plugboard.component.Component] constructor arguments.

    Attributes:
        name: The name of the `Component`.
        initial_values: Initial values for the `Component`.
        parameters: Parameters for the `Component`.
        constraints: Constraints for the `Component`.
        resources: Resource requirements for the `Component`.
    """

    name: str = Field(pattern=r"^([a-zA-Z_][a-zA-Z0-9_-]*)$")
    initial_values: dict[str, _t.Any] = {}
    parameters: dict[str, _t.Any] = {}
    constraints: dict[str, _t.Any] = {}
    resources: "Resource | None" = None


class ComponentSpec(PlugboardBaseModel):
    """Specification of a [`Component`][plugboard.component.Component].

    Attributes:
        type: The type of the `Component`.
        args: The arguments for the `Component`.
    """

    type: str
    args: ComponentArgsSpec
