"""Provides the `IOController` class for handling input/output operations."""

from enum import StrEnum
import typing as _t

from plugboard.channel import Channel
from plugboard.connector import Connector


IO_NS_UNSET = "__UNSET__"


class IODirection(StrEnum):
    """`IODirection` defines the type of IO operation."""

    INPUT = "input"
    OUTPUT = "output"


class IOController:
    """`IOController` manages input/output to/from component fields."""

    def __init__(self, inputs: _t.Any, outputs: _t.Any, namespace: str = IO_NS_UNSET) -> None:
        self.namespace = namespace
        self.inputs = inputs
        self.outputs = outputs
        self.data: dict[IODirection, dict[str, _t.Any]] = {
            IODirection.INPUT: {},
            IODirection.OUTPUT: {},
        }
        self._input_channels: dict[str, Channel] = {}
        self._output_channels: dict[str, Channel] = {}

    async def read(self) -> None:
        """Reads data from input channels."""
        for field, chan in self._input_channels.items():
            item = await chan.recv()
            self.data[IODirection.INPUT][field] = item

    async def write(self) -> None:
        """Writes data to output channels."""
        for field, chan in self._output_channels.items():
            item = self.data[IODirection.OUTPUT][field]
            await chan.send(item)

    def _add_channel_for_field(self, field: str, direction: IODirection, channel: Channel) -> None:
        io_fields = getattr(self, f"{direction}s")
        if field not in io_fields:
            raise ValueError(f"Unrecognised {direction} field {field}.")
        io_channels = getattr(self, f"_{direction}_channels")
        io_channels[field] = channel

    def _add_channel(self, conn: Connector) -> None:
        if conn.spec.source.component == self.namespace:
            self._add_channel_for_field(conn.spec.source.field, IODirection.OUTPUT, conn.channel)
        elif conn.spec.target.component == self.namespace:
            self._add_channel_for_field(conn.spec.target.field, IODirection.INPUT, conn.channel)

    def connect(self, connectors: list[Connector]) -> None:
        """Connects the input/output fields to input/output channels."""
        for conn in connectors:
            self._add_channel(conn)
