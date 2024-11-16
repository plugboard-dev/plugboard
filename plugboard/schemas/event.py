"""Provides models for events."""

from datetime import datetime, timezone
import re
import typing as _t
from uuid import uuid4

from pydantic import BaseModel, Field


_REGEX_UUID: str = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_REGEX_TIMESTAMP: str = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
_REGEX_EVENT_TYPE: str = r"^[a-zA-Z][a-zA-Z0-9_\-.]*$"


class EventUtils:
    """`EventUtils` provides helper functions for `Event`s."""

    @staticmethod
    def gen_id() -> str:
        """Generates a unique identifier for an event."""
        return str(uuid4())

    @staticmethod
    def gen_timestamp() -> str:
        """Generates a timestamp for an event in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()


class Event(BaseModel):
    """`Event` is a base model for all events."""

    type: _t.ClassVar[str]

    id: str = Field(
        default_factory=EventUtils.gen_id,
        pattern=_REGEX_UUID,
    )
    timestamp: str = Field(
        default_factory=EventUtils.gen_timestamp,
        pattern=_REGEX_TIMESTAMP,
    )
    source: str
    version: str = "0.1.0"
    data: dict[str, _t.Any] | BaseModel
    metadata: dict[str, str] = {}

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init_subclass__(*args, **kwargs)
        if not hasattr(cls, "type"):
            raise NotImplementedError(f"{cls.__name__} must define a `type` attribute.")
        if not re.match(_REGEX_EVENT_TYPE, cls.type):
            raise ValueError(f"Invalid event type: {cls.type}")
