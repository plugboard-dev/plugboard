"""Provides the `IOController` class for handling input/output operations."""

import asyncio
from collections import deque
import typing as _t

from plugboard.connector import Channel, Connector
from plugboard.events import Event
from plugboard.exceptions import ChannelClosedError, IOStreamClosedError
from plugboard.schemas.io import IODirection


IO_NS_UNSET = "__UNSET__"


class IOController:
    """`IOController` manages input/output to/from components."""

    def __init__(
        self,
        inputs: _t.Optional[_t.Any] = None,
        outputs: _t.Optional[_t.Any] = None,
        input_events: _t.Optional[list[_t.Type[Event]]] = None,
        output_events: _t.Optional[list[_t.Type[Event]]] = None,
        namespace: str = IO_NS_UNSET,
    ) -> None:
        self.namespace = namespace
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.input_events = input_events or []
        self.output_events = output_events or []
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
        self._input_event_channels: dict[str, Channel] = {}
        self._output_event_channels: dict[str, Channel] = {}
        self._input_event_types = {Event.safe_type(evt.type) for evt in self.input_events}
        self._output_event_types = {Event.safe_type(evt.type) for evt in self.output_events}
        self._read_tasks: dict[str, asyncio.Task] = {}
        self._is_closed = False

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `IOController` is closed, `False` otherwise."""
        return self._is_closed

    async def read(self) -> None:
        """Reads data and/or events from input channels.

        Read behaviour is dependent on the specific combination of input fields and events.
        If there are no input events, only input fields, then the method will only return
        once data has been received for all input fields. If there are input events, then
        the method will either return immediately when any event is received, or when data
        has been received for all input fields, whichever occurs first.
        """
        if self._is_closed:
            raise IOStreamClosedError("Attempted read on a closed io controller.")
        try:
            read_tasks = [asyncio.create_task(self._read_fields())]
            if len(self._input_event_channels) > 0:
                read_tasks.append(asyncio.create_task(self._read_events()))
            try:
                done, pending = await asyncio.wait(read_tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if (e := task.exception()) is not None:
                        raise e
                for task in pending:
                    task.cancel()
            except* ChannelClosedError as eg:
                await self.close()
                raise self._build_io_stream_error(IODirection.INPUT, eg) from eg
        except asyncio.CancelledError:
            for task in read_tasks:
                task.cancel()
            raise

    async def _read_fields(self) -> None:
        read_tasks = []
        for field, chan in self._input_channels.items():
            if field not in self._read_tasks:
                task = asyncio.create_task(self._read_field(field, chan))
                self._read_tasks[field] = task
            read_tasks.append(self._read_tasks[field])
        if len(read_tasks) == 0:
            return
        done, _ = await asyncio.wait(read_tasks, return_when=asyncio.ALL_COMPLETED)
        for field in self._input_channels.keys():
            self._read_tasks.pop(field)
        for task in done:
            if (e := task.exception()) is not None:
                raise e

    async def _read_field(self, field: str, chan: Channel) -> None:
        try:
            self.data[str(IODirection.INPUT)][field] = await chan.recv()
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    async def _read_events(self) -> None:
        read_tasks = []
        for event_type, chan in self._input_event_channels.items():
            if event_type not in self._read_tasks:
                task = asyncio.create_task(self._read_event(event_type, chan))
                task.set_name(event_type)
                self._read_tasks[event_type] = task
            read_tasks.append(self._read_tasks[event_type])
        if len(read_tasks) == 0:
            return
        done, _ = await asyncio.wait(read_tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            event_type = task.get_name()
            self._read_tasks.pop(event_type)
        for task in done:
            if (e := task.exception()) is not None:
                raise e

    async def _read_event(self, event_type: str, chan: Channel) -> None:
        try:
            self.events[str(IODirection.INPUT)].append(await chan.recv())
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for event: {event_type}") from e

    async def write(self) -> None:
        """Writes data to output channels."""
        if self._is_closed:
            raise IOStreamClosedError("Attempted write on a closed io controller.")
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._write_events())
                tg.create_task(self._write_fields())
        except* ChannelClosedError as eg:
            raise self._build_io_stream_error(IODirection.OUTPUT, eg) from eg

    async def _write_fields(self) -> None:
        async with asyncio.TaskGroup() as tg:
            for field, chan in self._output_channels.items():
                tg.create_task(self._write_field(field, chan))

    async def _write_field(self, field: str, chan: Channel) -> None:
        item = self.data[str(IODirection.OUTPUT)][field]
        try:
            await chan.send(item)
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    async def _write_events(self) -> None:
        queue = self.events[str(IODirection.OUTPUT)]
        async with asyncio.TaskGroup() as tg:
            for _ in range(len(queue)):
                event = queue.popleft()
                tg.create_task(self._write_event(event))

    async def _write_event(self, event: Event) -> None:
        try:
            chan = self._output_event_channels[event.type]
        except KeyError as e:
            raise ValueError(f"Unrecognised output event {event.type}.") from e
        try:
            await chan.send(event)
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for event: {event.type}.") from e

    def _build_io_stream_error(
        self, direction: IODirection, eg: ExceptionGroup
    ) -> IOStreamClosedError:
        inner_exc_msg = "\n\t".join([repr(e) for e in eg.exceptions])
        msg = f"Error reading {direction} for namespace: {self.namespace}\n\t{inner_exc_msg}"
        return IOStreamClosedError(msg)

    def queue_event(self, event: Event) -> None:
        """Queues an event for output."""
        if self._is_closed:
            raise IOStreamClosedError("Attempted queue_event on a closed io controller.")
        if event.type not in self._output_event_channels:
            raise ValueError(f"Unrecognised output event {event.type}.")
        self.events[str(IODirection.OUTPUT)].append(event)

    async def close(self) -> None:
        """Closes all input/output channels."""
        for chan in self._output_channels.values():
            await chan.close()
        for task in self._read_tasks.values():
            task.cancel()
        self._is_closed = True

    def _add_channel_for_field(self, field: str, direction: IODirection, channel: Channel) -> None:
        io_fields = getattr(self, f"{direction}s")
        if field not in io_fields:
            raise ValueError(f"Unrecognised {direction} field {field}.")
        io_channels = getattr(self, f"_{direction}_channels")
        io_channels[field] = channel

    def _add_channel_for_event(
        self, event_type: str, direction: IODirection, channel: Channel
    ) -> None:
        io_event_types = getattr(self, f"_{direction}_event_types")
        if event_type not in io_event_types:
            raise ValueError(f"Unrecognised {direction} event {event_type}.")
        io_channels = getattr(self, f"_{direction}_event_channels")
        io_channels[event_type] = channel

    def _add_channel(self, conn: Connector) -> None:
        if conn.spec.source.connects_to([self.namespace]):
            self._add_channel_for_field(
                conn.spec.source.descriptor, IODirection.OUTPUT, conn.channel
            )
        elif conn.spec.target.connects_to([self.namespace]):
            self._add_channel_for_field(
                conn.spec.target.descriptor, IODirection.INPUT, conn.channel
            )
        elif conn.spec.source.connects_to(self._output_event_types):
            self._add_channel_for_event(conn.spec.source.entity, IODirection.OUTPUT, conn.channel)
        elif conn.spec.target.connects_to(self._input_event_types):
            self._add_channel_for_event(conn.spec.target.entity, IODirection.INPUT, conn.channel)

    def connect(self, connectors: list[Connector]) -> None:
        """Connects the input/output fields to input/output channels."""
        for conn in connectors:
            self._add_channel(conn)
