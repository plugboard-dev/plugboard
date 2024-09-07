"""Connector submodule providing functionality related to component connectors and data exchange."""

from plugboard.connector.asyncio_channel import AsyncioChannel
from plugboard.connector.channel import Channel
from plugboard.connector.connector import Connector, ConnectorMode, ConnectorSpec


__all__ = [
    "Connector",
    "ConnectorSpec",
    "ConnectorMode",
    "Channel",
    "AsyncioChannel",
]
