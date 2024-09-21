"""Connector submodule providing functionality related to component connectors and data exchange."""

from plugboard.connector.asyncio_channel import AsyncioChannel, AsyncioChannelBuilder
from plugboard.connector.channel import Channel, ChannelClosedError
from plugboard.connector.channel_builder import ChannelBuilder, ChannelBuilderRegistry
from plugboard.connector.connector import Connector


__all__ = [
    "AsyncioChannel",
    "AsyncioChannelBuilder",
    "Connector",
    "Channel",
    "ChannelBuilder",
    "ChannelBuilderRegistry",
    "ChannelClosedError",
]
