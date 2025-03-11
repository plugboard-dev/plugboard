"""Provides base model for events and helper functionality."""

from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
import re
import typing as _t
from uuid import UUID, uuid4

from pydantic import UUID4, BaseModel, Field
from pydantic.functional_validators import AfterValidator

from plugboard.events.event_handlers import EventHandlers
from plugboard.schemas._common import PlugboardBaseModel
from plugboard.utils.types import AsyncCallable


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


class Event(PlugboardBaseModel, ABC):
    """`Event` is a base model for all events.

    Attributes:
        type: Type of the `Event`.
        id: UUID v4 unique identifier for the `Event`.
        timestamp: UTC timestamp for the `Event`.
        source: Source of the `Event`.
        version: Version of the `Event`.
        data: Data associated with the `Event`.
        metadata: Metadata for the `Event`.
    """

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

    @classmethod
    def safe_type(cls, event_type: _t.Optional[str] = None) -> str:
        """Returns a safe event type string for use in broker topic strings."""
        return (event_type or cls.type).replace(".", "_").replace("-", "_")

    @classmethod
    def handler(cls, method: AsyncCallable) -> AsyncCallable:
        """Registers a class method as an event handler."""
        return EventHandlers.add(cls)(method)


class SystemEvent(Event, ABC):
    """`SystemEvent` is a base model for system events.

    Attributes:
        type: Type of the `SystemEvent`.
        id: UUID v4 unique identifier for the `SystemEvent`.
        timestamp: UTC timestamp for the `SystemEvent`.
        source: Source of the `SystemEvent`.
        version: Version of the `SystemEvent`.
        data: Data associated with the `SystemEvent`.
        metadata: Metadata for the `SystemEvent`.
    """

    type: _t.ClassVar[str] = "system"


class StopEvent(SystemEvent):
    """`StopEvent` is a system event to stop the application."""

    type: _t.ClassVar[str] = "system.stop"
