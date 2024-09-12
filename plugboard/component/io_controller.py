"""Provides the `IOController` class for handling input/output operations."""

from enum import StrEnum
import typing as _t

from plugboard.connector import Channel, ChannelClosedError, Connector


IO_NS_UNSET = "__UNSET__"


class IOStreamClosedError(Exception):
    """`IOStreamClosedError` is raised when an IO stream is closed."""

    pass


class IODirection(StrEnum):
    """`IODirection` defines the type of IO operation."""

    INPUT = "input"
    OUTPUT = "output"


class IOController:
    """`IOController` manages input/output to/from component fields."""

    def __init__(
        self,
        inputs: _t.Optional[_t.Any] = None,
        outputs: _t.Optional[_t.Any] = None,
        namespace: str = IO_NS_UNSET,
    ) -> None:
        self.namespace = namespace
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.data: dict[str, dict[str, _t.Any]] = {
            IODirection.INPUT: {},
            IODirection.OUTPUT: {},
        }
        self._input_channels: dict[str, Channel] = {}
        self._output_channels: dict[str, Channel] = {}
        self._is_closed = False

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `IOController` is closed, `False` otherwise."""
        return self._is_closed

    async def read(self) -> None:
        """Reads data from input channels."""
        if self._is_closed:
            raise IOStreamClosedError()
        for field, chan in self._input_channels.items():
            try:
                item = await chan.recv()
            except ChannelClosedError:
                await self.close()
                raise IOStreamClosedError(f"Channel for field {field} is closed.")
            self.data[IODirection.INPUT][field] = item

    async def write(self) -> None:
        """Writes data to output channels."""
        if self._is_closed:
            raise IOStreamClosedError()
        for field, item in self.data[IODirection.OUTPUT].items():
            chan = self._output_channels[field]
            if chan.is_closed:
                raise IOStreamClosedError(f"Channel for field {field} is closed.")
            await chan.send(item)

    async def close(self) -> None:
        """Closes all input/output channels."""
        for chan in self._output_channels.values():
            await chan.close()
        self._is_closed = True

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
