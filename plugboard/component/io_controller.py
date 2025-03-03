"""Provides the `IOController` class for handling input/output operations."""

import asyncio
from collections import deque
from functools import cached_property
import typing as _t

from plugboard.connector import AsyncioChannel, Channel, Connector
from plugboard.events import Event
from plugboard.exceptions import ChannelClosedError, IOStreamClosedError
from plugboard.schemas.io import IODirection
from plugboard.utils import DI


IO_NS_UNSET = "__UNSET__"

_io_key_in: str = str(IODirection.INPUT)
_io_key_out: str = str(IODirection.OUTPUT)
_fields_read_task: str = "__READ_FIELDS__"
_events_read_task: str = "__READ_EVENTS__"
_events_wait_task: str = "__AWAIT_EVENTS__"


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
        self.data: dict[str, dict[str, _t.Any]] = {_io_key_in: {}, _io_key_out: {}}
        self.events: dict[str, deque[Event]] = {_io_key_in: deque(), _io_key_out: deque()}
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

        self._received_events: deque[Event] = deque()
        self._has_received_events = asyncio.Event()
        self._has_received_events_lock = asyncio.Lock()

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `IOController` is closed, `False` otherwise."""
        return self._is_closed

    @cached_property
    def _has_field_inputs(self) -> bool:
        return len(self._input_channels) > 0

    @cached_property
    def _has_field_outputs(self) -> bool:
        return len(self._output_channels) > 0

    @cached_property
    def _has_event_inputs(self) -> bool:
        return len(self._input_event_channels) > 0

    async def read(self) -> None:
        """Reads data and/or events from input channels.

        Read behaviour is dependent on the specific combination of input fields, output fields,
        and input events. In general, all components will have at a minimum the system defined
        input events, such as `StopEvent`. Logic for the various cases is as follows:

        - At least one input field: the method waits until either all input fields have received
          data or an input event is received, and returns after whichever occurs first.
        - No input fields but at least one output field: the method waits for a short amount of
          time to give chance for input events to be received before returning so that the control
          flow can continue on to processing output events.
        - No input fields or output fields: this is the pure event driven case where the method
          waits until an input event is received, and returns after the first received event.
        """
        if self._is_closed:
            raise IOStreamClosedError("Attempted read on a closed io controller.")
        if len(read_tasks := self._set_read_tasks()) == 0:
            return
        # If there are field outputs but not inputs, wait for a short time to receive input events
        timeout = 1e-3 if self._has_field_outputs and not self._has_field_inputs else None
        try:
            try:
                done, _ = await asyncio.wait(
                    read_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout
                )
                for task in done:
                    if (e := task.exception()) is not None:
                        raise e
                    self._read_tasks.pop(task.get_name())
                    self._set_read_tasks()
                    await self._flush_event_buffer()
            except* ChannelClosedError as eg:
                await self.close()
                raise self._build_io_stream_error(IODirection.INPUT, eg) from eg
        except asyncio.CancelledError:
            for task in read_tasks:
                task.cancel()
            raise

    def _set_read_tasks(self) -> list[asyncio.Task]:
        read_tasks: list[asyncio.Task] = []
        if self._has_field_inputs:
            if _fields_read_task not in self._read_tasks:
                read_fields_task = asyncio.create_task(self._read_fields())
                read_fields_task.set_name(_fields_read_task)
                self._read_tasks[_fields_read_task] = read_fields_task
            read_tasks.append(self._read_tasks[_fields_read_task])
        if self._has_event_inputs:
            if _events_read_task not in self._read_tasks:
                read_events_task = asyncio.create_task(self._read_events())
                read_events_task.set_name(_events_read_task)
                self._read_tasks[_events_read_task] = read_events_task
            if _events_wait_task not in self._read_tasks:
                wait_for_events_task = asyncio.create_task(self._has_received_events.wait())
                wait_for_events_task.set_name(_events_wait_task)
                self._read_tasks[_events_wait_task] = wait_for_events_task
            read_tasks.append(self._read_tasks[_events_wait_task])
        return read_tasks

    async def _flush_event_buffer(self) -> None:
        if self._has_received_events.is_set():
            async with self._has_received_events_lock:
                self._has_received_events.clear()
                self.events[_io_key_in].extend(self._received_events)
                self._received_events.clear()

    async def _read_fields(
        self,
    ) -> None:
        read_tasks = []
        for (key, _), chan in self._input_channels.items():
            # FIXME : Looks like multiple channels for same field will trample each other
            if key not in self._read_tasks:
                task = asyncio.create_task(self._read_channel("field", key, chan))
                task.set_name(key)
                self._read_tasks[key] = task
            read_tasks.append(self._read_tasks[key])
        if len(read_tasks) == 0:
            return
        done, _ = await asyncio.wait(read_tasks, return_when=asyncio.ALL_COMPLETED)
        for task in done:
            key = task.get_name()
            self._read_tasks.pop(key)
            if (e := task.exception()) is not None:
                raise e
            self.data[_io_key_in][key] = task.result()

    async def _read_events(self) -> None:
        fan_in = AsyncioChannel()

        async def _iter_event_channel(chan: Channel) -> None:
            while True:
                result = await chan.recv()
                await fan_in.send(result)

        async with asyncio.TaskGroup() as tg:
            for chan in self._input_event_channels.values():
                tg.create_task(_iter_event_channel(chan))

            while True:
                event = await fan_in.recv()
                async with self._has_received_events_lock:
                    self._received_events.append(event)
                    self._has_received_events.set()

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
        item = self.data[_io_key_out][field]
        try:
            await channel.send(item)
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    async def _write_events(self) -> None:
        queue = self.events[_io_key_out]
        async with asyncio.TaskGroup() as tg:
            for _ in range(len(queue)):
                event = queue.popleft()
                tg.create_task(self._write_event(event))

    async def _write_event(self, event: Event) -> None:
        try:
            chan = self._output_event_channels[event.safe_type()]
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
        if event.safe_type() not in self._output_event_channels:
            raise ValueError(f"Unrecognised output event {event.type}.")
        self.events[_io_key_out].append(event)

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
        self._validate_connections()
        self._logger.info("IOController connected")

    def _validate_connections(self) -> None:
        connected_inputs = set(k for k, _ in self._input_channels.keys())
        connected_outputs = set(k for k, _ in self._output_channels.keys())
        if unconnected_inputs := set(self.inputs) - connected_inputs:
            self._logger.error(
                "Input fields not connected, process may hang", unconnected=unconnected_inputs
            )
        if unconnected_outputs := set(self.outputs) - connected_outputs:
            self._logger.warning("Output fields not connected", unconnected=unconnected_outputs)
