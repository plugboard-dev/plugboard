"""Provides top-level `ConfigSpec` class for Plugboard configuration."""

from pydantic import BaseModel

from .process import ProcessSpec


class ProcessConfigSpec(BaseModel):
    """A `ProcessSpec` within a Plugboard configuration.

    Attributes:
        process: A `ProcessSpec` that specifies the process.
    """

    process: ProcessSpec


class ConfigSpec(BaseModel):
    """Configuration for a Plugboard simulation.

    Attributes:
        plugboard: A `ProcessConfig` that specifies the Plugboard `Process`.
    """

    plugboard: ProcessConfigSpec
