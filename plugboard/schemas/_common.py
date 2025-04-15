"""Common classes for Plugboard schemas."""

from abc import ABC
import typing as _t

from pydantic import BaseModel, ConfigDict


class PlugboardBaseModel(BaseModel, ABC):
    """Custom base model for Plugboard schemas."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, use_enum_values=True, validate_assignment=True
    )

    def override(self, location: str, value: _t.Any) -> None:
        """Set the value of the attribute at the namespaces `location`."""
        # if "." not in location:
        #     # Set the field on this object
        #     setattr(self, location, value)
        #     return
        # field_name, sub_location = location.split(".", 1)
        # override_field = getattr(self, field_name)
        # if isinstance(override_field, dict) and "." not in sub_location:
        #     # Handle the case where we need to change item in a dict
        #     override_field[sub_location] = value
        #     return
        # # Otherwise recursively override the sub-location
        # if isinstance(override_field, PlugboardBaseModel):
        #     match = override_field
        # elif isinstance(override_field, dict):
        #     match = override_field[sub_location]
        # elif isinstance(override_field, list):
        #     # Match the list item by name
        #     try:
        #         match = next(
        #             obj
        #             for obj in override_field
        #             # Match either name or args.name
        #             if getattr(obj, "name") == sub_location
        #             or getattr(getattr(obj, "args"), "name") == sub_location
        #         )
        #     except (StopIteration, AttributeError):
        #         raise ValueError(f"Cannot find item named {sub_location} in {override_field}")
        # if isinstance(match, PlugboardBaseModel):
        #     # Recursively override the sub-location
        #     match.override(sub_location, value)
        # raise ValueError(f"Cannot override {sub_location} on {override_field}")
