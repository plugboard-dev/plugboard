"""Connector submodule providing functionality related to component connectors and data exchange."""

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import Channel, ChannelClosedError
from plugboard.connector.connector import Connector


__all__ = [
    "Connector",
    "Channel",
    "AsyncioChannel",
    "ChannelClosedError",
]
