"""Provides base model for events and helper functionality."""

from datetime import datetime, timezone
import re
import typing as _t
from uuid import UUID, uuid4

from pydantic import UUID4, BaseModel, Field
from pydantic.functional_validators import AfterValidator


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


UTCDateTime = _t.Annotated[datetime, AfterValidator(_ensure_utc)]

_REGEX_EVENT_TYPE: str = r"^[a-zA-Z][a-zA-Z0-9_\-.]*$"


class EventUtils:
    """`EventUtils` provides helper functions for `Event`s."""

    @staticmethod
    def gen_id() -> UUID:
        """Generates a unique identifier for an event."""
        return uuid4()

    @staticmethod
    def gen_timestamp() -> datetime:
        """Generates a timestamp string for an event in ISO 8601 format."""
        return datetime.now(timezone.utc)


class Event(BaseModel):
    """`Event` is a base model for all events."""

    type: _t.ClassVar[str]

    id: UUID4 = Field(default_factory=EventUtils.gen_id)
    timestamp: UTCDateTime = Field(default_factory=EventUtils.gen_timestamp)
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

    @staticmethod
    def safe_type(event_type: str) -> str:
        """Returns a safe event type string for use in broker topic strings."""
        return event_type.replace(".", "_").replace("-", "_")
