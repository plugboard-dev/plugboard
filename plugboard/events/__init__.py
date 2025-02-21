"""Provides models and utilities for handling events."""

from plugboard.events.event import Event, StopEvent, SystemEvent
from plugboard.events.event_connector_builder import EventConnectorBuilder
from plugboard.events.event_handlers import EventHandlers


__all__ = [
    "Event",
    "EventConnectorBuilder",
    "EventHandlers",
    "StopEvent",
    "SystemEvent",
]
