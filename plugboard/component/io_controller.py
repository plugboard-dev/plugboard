"""Provides the `IOController` class for handling input/output operations."""

import asyncio
from collections import deque
import typing as _t

from plugboard.connector import Channel, Connector
from plugboard.exceptions import ChannelClosedError, IOStreamClosedError
from plugboard.schemas.event import Event
from plugboard.schemas.io import IODirection


IO_NS_UNSET = "__UNSET__"


class IOController:
    """`IOController` manages input/output to/from components."""

    def __init__(
        self,
        inputs: _t.Optional[_t.Any] = None,
        outputs: _t.Optional[_t.Any] = None,
        input_events: _t.Optional[list[Event]] = None,
        output_events: _t.Optional[list[Event]] = None,
        namespace: str = IO_NS_UNSET,
    ) -> None:
        self.namespace = namespace
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.data: dict[str, dict[str, _t.Any]] = {
            str(IODirection.INPUT): {},
            str(IODirection.OUTPUT): {},
        }
        self.events: dict[str, deque[Event]] = {
            str(IODirection.INPUT): deque(),
            str(IODirection.OUTPUT): deque(),
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
            raise IOStreamClosedError("Attempted read on a closed io controller.")
        try:
            async with asyncio.TaskGroup() as tg:
                for field, chan in self._input_channels.items():
                    tg.create_task(self._read_channel_handler(field, chan))
        except* ChannelClosedError as eg:
            await self.close()
            raise self._build_io_stream_error(IODirection.INPUT, eg) from eg

    async def _read_channel_handler(self, field: str, chan: Channel) -> None:
        try:
            self.data[str(IODirection.INPUT)][field] = await chan.recv()
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    async def write(self) -> None:
        """Writes data to output channels."""
        if self._is_closed:
            raise IOStreamClosedError("Attempted write on a closed io controller.")
        try:
            async with asyncio.TaskGroup() as tg:
                for field, chan in self._output_channels.items():
                    tg.create_task(self._write_channel_handler(field, chan))
        except* ChannelClosedError as eg:
            raise self._build_io_stream_error(IODirection.OUTPUT, eg) from eg

    async def _write_channel_handler(self, field: str, chan: Channel) -> None:
        item = self.data[str(IODirection.OUTPUT)][field]
        try:
            await chan.send(item)
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    def _build_io_stream_error(
        self, direction: IODirection, eg: ExceptionGroup
    ) -> IOStreamClosedError:
        inner_exc_msg = "\n\t".join([repr(e) for e in eg.exceptions])
        msg = f"Error reading {direction} for namespace: {self.namespace}\n\t{inner_exc_msg}"
        return IOStreamClosedError(msg)

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
