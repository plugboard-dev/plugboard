"""Provides the `IOController` class for handling input/output operations."""

import asyncio
from collections import deque
import typing as _t

from plugboard.connector import Channel, Connector
from plugboard.events import Event
from plugboard.exceptions import ChannelClosedError, IOStreamClosedError
from plugboard.schemas.io import IODirection
from plugboard.utils import DI


IO_NS_UNSET = "__UNSET__"


class IOController:
    """`IOController` manages input/output to/from components."""

    def __init__(
        self,
        inputs: _t.Optional[_t.Any] = None,
        outputs: _t.Optional[_t.Any] = None,
        initial_values: _t.Optional[dict[str, _t.Iterable]] = None,
        input_events: _t.Optional[list[_t.Type[Event]]] = None,
        output_events: _t.Optional[list[_t.Type[Event]]] = None,
        namespace: str = IO_NS_UNSET,
    ) -> None:
        self.namespace = namespace
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.initial_values = initial_values or {}
        self.input_events = input_events or []
        self.output_events = output_events or []
        if set(self.initial_values.keys()) - set(self.inputs):
            raise ValueError("Initial values must be for input fields only.")
        self.data: dict[str, dict[str, _t.Any]] = {
            str(IODirection.INPUT): {},
            str(IODirection.OUTPUT): {},
        }
        self.events: dict[str, deque[Event]] = {
            str(IODirection.INPUT): deque(),
            str(IODirection.OUTPUT): deque(),
        }
        self._input_channels: dict[tuple[str, str], Channel] = {}
        self._output_channels: dict[tuple[str, str], Channel] = {}
        self._input_event_channels: dict[str, Channel] = {}
        self._output_event_channels: dict[str, Channel] = {}
        self._input_event_types = {Event.safe_type(evt.type) for evt in self.input_events}
        self._output_event_types = {Event.safe_type(evt.type) for evt in self.output_events}
        self._read_tasks: dict[str, asyncio.Task] = {}
        self._initial_values = {k: deque(v) for k, v in self.initial_values.items()}
        self._is_closed = False
        self._logger = DI.logger.sync_resolve().bind(
            cls=self.__class__.__name__, namespace=self.namespace
        )
        self._logger.info("IOController created")

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
        read_tasks = []
        if len(self._input_channels) > 0:
            task = asyncio.create_task(self._read_fields())
            read_tasks.append(task)
        if len(self._input_event_channels) > 0:
            task = asyncio.create_task(self._read_events())
            read_tasks.append(task)
        if len(read_tasks) == 0:
            return
        try:
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
        await self._read_channel_set(
            channel_type="field",
            channels=self._input_channels,
            return_when=asyncio.ALL_COMPLETED,
            store_fn=lambda k, v: self.data[str(IODirection.INPUT)].update({k: v}),
        )

    async def _read_events(self) -> None:
        await self._read_channel_set(
            channel_type="event",
            channels={(k, ""): ch for k, ch in self._input_event_channels.items()},
            return_when=asyncio.FIRST_COMPLETED,
            store_fn=lambda _, v: self.events[str(IODirection.INPUT)].append(v),
        )

    async def _read_channel_set(
        self,
        channel_type: str,
        channels: dict[tuple[str, str], Channel],
        return_when: str,
        store_fn: _t.Callable[[str, _t.Any], None],
    ) -> None:
        read_tasks = []
        for (key, _), chan in channels.items():
            if key not in self._read_tasks:
                task = asyncio.create_task(self._read_channel(channel_type, key, chan))
                task.set_name(key)
                self._read_tasks[key] = task
            read_tasks.append(self._read_tasks[key])
        if len(read_tasks) == 0:
            return
        done, _ = await asyncio.wait(read_tasks, return_when=return_when)
        for task in done:
            key = task.get_name()
            self._read_tasks.pop(key)
            if (e := task.exception()) is not None:
                raise e
            store_fn(key, task.result())

    async def _read_channel(self, channel_type: str, key: str, channel: Channel) -> _t.Any:
        try:
            # Use an initial value if available
            return self._initial_values[key].popleft()
        except (IndexError, KeyError):
            pass
        try:
            return await channel.recv()
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for {channel_type}: {key}.") from e

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
            for (field, _), chan in self._output_channels.items():
                tg.create_task(self._write_field(field, chan))

    async def _write_field(self, field: str, channel: Channel) -> None:
        item = self.data[str(IODirection.OUTPUT)][field]
        try:
            await channel.send(item)
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
        self._logger.info("IOController closed")

    def _add_channel_for_field(
        self, field: str, connector_id: str, direction: IODirection, channel: Channel
    ) -> None:
        io_fields = getattr(self, f"{direction}s")
        if field not in io_fields:
            raise ValueError(f"Unrecognised {direction} field {field}.")
        io_channels = getattr(self, f"_{direction}_channels")
        io_channels[(field, connector_id)] = channel

    def _add_channel_for_event(
        self, event_type: str, direction: IODirection, channel: Channel
    ) -> None:
        io_event_types = getattr(self, f"_{direction}_event_types")
        if event_type not in io_event_types:
            raise ValueError(f"Unrecognised {direction} event {event_type}.")
        io_channels = getattr(self, f"_{direction}_event_channels")
        io_channels[event_type] = channel

    async def _add_channel(self, connector: Connector) -> None:
        if connector.spec.source.connects_to([self.namespace]):
            channel = await connector.connect_send()
            self._add_channel_for_field(
                connector.spec.source.descriptor, connector.spec.id, IODirection.OUTPUT, channel
            )
        if connector.spec.target.connects_to([self.namespace]):
            channel = await connector.connect_recv()
            self._add_channel_for_field(
                connector.spec.target.descriptor, connector.spec.id, IODirection.INPUT, channel
            )
        if connector.spec.source.connects_to(self._output_event_types):
            channel = await connector.connect_send()
            self._add_channel_for_event(connector.spec.source.entity, IODirection.OUTPUT, channel)
        if connector.spec.target.connects_to(self._input_event_types):
            channel = await connector.connect_recv()
            self._add_channel_for_event(connector.spec.target.entity, IODirection.INPUT, channel)

    async def connect(self, connectors: list[Connector]) -> None:
        """Connects the input/output fields to input/output channels."""
        async with asyncio.TaskGroup() as tg:
            for conn in connectors:
                tg.create_task(self._add_channel(conn))
        connected_inputs = set(k for k, _ in self._input_channels.keys())
        connected_outputs = set(k for k, _ in self._output_channels.keys())
        if unconnected_inputs := set(self.inputs) - connected_inputs:
            self._logger.error(
                "Input fields not connected, process may hang", unconnected=unconnected_inputs
            )
        if unconnected_outputs := set(self.outputs) - connected_outputs:
            self._logger.warning("Output fields not connected", unconnected=unconnected_outputs)
        self._logger.info("IOController connected")
