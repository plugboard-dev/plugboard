"""Provides top-level `ConfigSpec` class for Plugboard configuration."""

from plugboard.schemas._common import PlugboardBaseModel
from .process import ProcessSpec


class ProcessConfigSpec(PlugboardBaseModel):
    """A `ProcessSpec` within a Plugboard configuration.

    Attributes:
        process: A `ProcessSpec` that specifies the process.
    """

    process: ProcessSpec


class ConfigSpec(PlugboardBaseModel):
    """Configuration for a Plugboard simulation.

    Attributes:
        plugboard: A `ProcessConfig` that specifies the Plugboard `Process`.
    """

    plugboard: ProcessConfigSpec
