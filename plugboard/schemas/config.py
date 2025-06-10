"""Provides top-level `ConfigSpec` class for Plugboard configuration."""

from pathlib import Path
import typing as _t

import msgspec
from pydantic import field_validator

from plugboard.schemas._common import PlugboardBaseModel
from .process import ProcessSpec
from .tune import TuneSpec


class ProcessConfigSpec(PlugboardBaseModel):
    """A `ProcessSpec` within a Plugboard configuration.

    Attributes:
        process: A `ProcessSpec` that specifies the process, or a path to a YAML file containing the
            process specification.
        tune: Optional; A `TuneSpec` that specifies an optimisation configuration.
    """

    process: ProcessSpec
    tune: TuneSpec | None = None

    @field_validator("process", mode="before")
    @classmethod
    def _auto_load_process(cls, value: _t.Any) -> _t.Any:
        """Automatically loads the process specification from a YAML file if a path is provided."""
        if isinstance(value, str) and Path(value).exists():
            with open(value, "rb") as f:
                other_config = msgspec.yaml.decode(f.read())
            try:
                return other_config["plugboard"]["process"]
            except KeyError:
                raise ValueError(
                    "The provided YAML file does not contain a Plugboard process specification."
                )
        return value


class ConfigSpec(PlugboardBaseModel):
    """Configuration for a Plugboard simulation.

    Attributes:
        plugboard: A `ProcessConfig` that specifies the Plugboard `Process`.
    """

    plugboard: ProcessConfigSpec
