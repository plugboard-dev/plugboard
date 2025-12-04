"""Common classes for Plugboard schemas."""

from abc import ABC

from pydantic import BaseModel, ConfigDict


class PlugboardBaseModel(BaseModel, ABC):
    """Custom base model for Plugboard schemas."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, use_enum_values=True, validate_assignment=True
    )
