"""Provides `ComponentSpec` class."""

import re
import typing as _t

from pydantic import Field, field_validator

from ._common import PlugboardBaseModel


def _parse_resource_value(value: str | float | int) -> float:
    """Parse a resource value from string or number.

    Supports:
    - Direct numerical values: 1, 0.5, 2.0
    - Milli-units: "250m" -> 0.25
    - Memory units: "10Mi" -> 10485760 (10 * 1024 * 1024)
    - Memory units: "10Gi" -> 10737418240 (10 * 1024 * 1024 * 1024)

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

    # Handle milli-units (e.g., "250m" -> 0.25)
    if value.endswith("m"):
        match = re.match(r"^(\d+(?:\.\d+)?)m$", value)
        if match:
            return float(match.group(1)) / 1000.0
        raise ValueError(f"Invalid milli-unit format: {value}")

    # Handle memory units
    # Ki = 1024, Mi = 1024^2, Gi = 1024^3, Ti = 1024^4
    memory_units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }

    for suffix, multiplier in memory_units.items():
        if value.endswith(suffix):
            # Use re.escape to safely escape the suffix in the regex pattern
            pattern = rf"^(\d+(?:\.\d+)?){re.escape(suffix)}$"
            match = re.match(pattern, value)
            if match:
                return float(match.group(1)) * multiplier
            raise ValueError(f"Invalid memory unit format: {value}")

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
        memory: Memory requirement in bytes (default: 0).
        resources: Custom resource requirements as a dictionary.
    """

    cpu: float = 0.001
    gpu: float = 0
    memory: float = 0
    resources: dict[str, float] = Field(default_factory=dict)

    @field_validator("cpu", "gpu", "memory", mode="before")
    @classmethod
    def _parse_resource_field(cls, v: str | float | int) -> float:
        """Validate and parse resource fields."""
        return _parse_resource_value(v)

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
    resources: _t.NotRequired["Resource | None"]


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
