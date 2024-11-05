"""Provides models for events."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


_REGEX_UUID: str = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_REGEX_TIMESTAMP: str = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"


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

    id: str = Field(
        default_factory=EventUtils.gen_id,
        pattern=_REGEX_UUID,
    )
    timestamp: str = Field(
        default_factory=EventUtils.gen_timestamp,
        pattern=_REGEX_TIMESTAMP,
    )
    type: str
    source: str
    version: str = "0.1.0"
    data: dict[str, str]
    metadata: dict[str, str] = {}
