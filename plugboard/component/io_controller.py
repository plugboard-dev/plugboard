"""Provides the `IOController` class for handling input/output operations."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from functools import cache, cached_property
import typing as _t

from plugboard.connector import AsyncioChannel, Channel, Connector
from plugboard.events import Event, StopEvent
from plugboard.exceptions import ChannelClosedError, IOStreamClosedError
from plugboard.schemas.io import IODirection
from plugboard.utils import DI


if _t.TYPE_CHECKING:  # pragma: no cover
    from plugboard.component import Component

IO_NS_UNSET: str = "__UNSET__"
IO_CLOSE_GRACE_PERIOD: float = 3.0

_t_field_key = tuple[str, str]
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
        component: _t.Optional[Component] = None,
    ) -> None:
        self.namespace = namespace
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.initial_values = initial_values or {}
        self.input_events = input_events or []
        self.output_events = output_events or []
        if set(self.initial_values.keys()) - set(self.inputs):
            raise ValueError("Initial values must be for input fields only.")
        self._component = component

        self.buf_fields: dict[str, IOBuffer] = {
            _io_key_in: IOFieldBuffer(),
            _io_key_out: IOFieldBuffer(),
        }
        self.buf_events: dict[str, IOBuffer] = {
            _io_key_in: IOEventBuffer(),
            _io_key_out: IOEventBuffer(),
        }

        self._input_channels: dict[tuple[str, str], Channel] = {}
        self._output_channels: dict[tuple[str, str], Channel] = {}
        self._input_event_channels: dict[str, Channel] = {}
        self._output_event_channels: dict[str, Channel] = {}
        self._input_event_types = {Event.safe_type(evt.type) for evt in self.input_events}
        self._output_event_types = {Event.safe_type(evt.type) for evt in self.output_events}
        self._initial_values = {k: deque(v) for k, v in self.initial_values.items()}
        self._read_tasks: dict[str | _t_field_key, asyncio.Task] = {}
        self._is_closed = False

        self._logger = DI.logger.resolve_sync().bind(
            cls=self.__class__.__name__, namespace=self.namespace
        )
        self._logger.info("IOController created")

        self._received_fields: dict[str, _t.Any] = {}
        self._received_fields_lock = asyncio.Lock()
        self._received_events: deque[Event] = deque()
        self._received_events_lock = asyncio.Lock()
        self._has_received_events = asyncio.Event()

    @property
    def is_closed(self) -> bool:
        """Returns `True` if the `IOController` is closed, `False` otherwise."""
        return self._is_closed

    @cached_property
    def _has_field_inputs(self) -> bool:
        return len(self._input_channels) > 0

    @cached_property
    def _has_event_inputs(self) -> bool:
        return len(self._input_event_channels) > 0

    @cached_property
    def _has_inputs(self) -> bool:
        return self._has_field_inputs or self._has_event_inputs

    async def read(self, timeout: float | None = None) -> None:
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
        try:
            try:
                done, _ = await asyncio.wait(
                    read_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout
                )
                for task in done:
                    if (e := task.exception()) is not None:
                        raise e
                    self._read_tasks.pop(task.get_name())
                await self._flush_internal_field_buffer()
                await self._flush_internal_event_buffer()
                self._set_read_tasks()
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
                read_fields_task = asyncio.create_task(self._read_fields(), name=_fields_read_task)
                self._read_tasks[_fields_read_task] = read_fields_task
            read_tasks.append(self._read_tasks[_fields_read_task])
        if self._has_event_inputs:
            if _events_read_task not in self._read_tasks:
                read_events_task = asyncio.create_task(self._read_events(), name=_events_read_task)
                self._read_tasks[_events_read_task] = read_events_task
            if _events_wait_task not in self._read_tasks:
                wait_for_events_task = asyncio.create_task(
                    self._has_received_events.wait(), name=_events_wait_task
                )
                self._read_tasks[_events_wait_task] = wait_for_events_task
            read_tasks.append(self._read_tasks[_events_wait_task])
        return read_tasks

    async def _flush_internal_field_buffer(self) -> None:
        async with self._received_fields_lock:
            self.buf_fields[_io_key_in].put(self._received_fields.items())
            self._received_fields = {}

    async def _flush_internal_event_buffer(self) -> None:
        if self._has_received_events.is_set():
            async with self._received_events_lock:
                self._has_received_events.clear()
                events = sorted(self._received_events, key=lambda e: e.timestamp)
                self.buf_events[_io_key_in].put(events)
                self._received_events.clear()

    async def _read_fields(self) -> None:
        if self._received_fields:
            return  # Don't read new data if buffered input data has not been consumed

        read_tasks: dict[str, asyncio.Task] = {}

        for key in self._input_channels:
            field, _ = key
            _key = (field, _io_key_in) if f"group:{field}" in self._read_tasks else key
            task_name = f"field:{_key}"
            if task_name not in self._read_tasks:
                task = asyncio.create_task(
                    self._read_field(_key, self._input_channels[_key]), name=task_name
                )
                self._read_tasks[task_name] = task
            read_tasks[task_name] = self._read_tasks[task_name]
        if len(read_tasks.keys()) == 0:
            return

        done, _ = await asyncio.wait(read_tasks.values(), return_when=asyncio.ALL_COMPLETED)

        async with self._received_fields_lock:
            for task in done:
                task_name = task.get_name()
                self._read_tasks.pop(task_name)
                if (e := task.exception()) is not None:
                    raise e
                key, data = task.result()
                field, _ = key
                self._received_fields[field] = data

    async def _read_field_group(
        self, field_channels: list[tuple[_t_field_key, Channel]], fan_in: AsyncioChannel
    ) -> None:
        """Reads a group of fields and sends the results to a fan-in channel."""

        async def _iter_field_channel(key: _t_field_key, chan: Channel) -> None:
            while True:
                try:
                    _, result = await self._read_field(key, chan)
                except ChannelClosedError:
                    break
                await fan_in.send(result)

        async with asyncio.TaskGroup() as tg:
            for key, chan in field_channels:
                tg.create_task(_iter_field_channel(key, chan))

        await fan_in.close()

    async def _read_field(self, key: _t_field_key, channel: Channel) -> tuple[_t_field_key, _t.Any]:
        """Reads a single field and returns the key and result."""
        field, _ = key
        try:
            # Use an initial value if available
            return key, self._initial_values[field].popleft()
        except (IndexError, KeyError):
            pass
        try:
            return key, await channel.recv()
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {key}.") from e

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
                async with self._received_events_lock:
                    self._received_events.append(event)
                    self._has_received_events.set()

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
        if not self.buf_fields[_io_key_out]:
            return  # Don't attempt to write data if no data added to the output buffer
        buffer = dict(self.buf_fields[_io_key_out].flush())
        async with asyncio.TaskGroup() as tg:
            for (field, _), chan in self._output_channels.items():
                tg.create_task(self._write_field(field, chan, buffer[field]))

    async def _write_field(self, field: str, channel: Channel, item: _t.Any) -> None:
        try:
            await channel.send(item)
        except ChannelClosedError as e:
            raise ChannelClosedError(f"Channel closed for field: {field}.") from e

    async def _write_events(self) -> None:
        queue = deque(self.buf_events[_io_key_out].flush())
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
        self.buf_events[_io_key_out].put([event])

    async def close(self) -> None:
        """Closes all input/output channels."""
        async with asyncio.TaskGroup() as tg:
            for chan in self._output_channels.values():
                tg.create_task(chan.close())
        for task in self._read_tasks.values():
            task.cancel()
        # If there are events to read wait some grace period before flushing event buffer
        if self._input_event_types - {StopEvent.safe_type()}:
            await asyncio.sleep(IO_CLOSE_GRACE_PERIOD)
            await self._flush_internal_event_buffer()
        self._is_closed = True
        self._logger.info("IOController closed")

    async def connect(self, connectors: list[Connector]) -> None:
        """Connects the input/output fields to input/output channels."""
        if self._component is None:
            raise RuntimeError("IOController must be bound to a component before connecting.")
        # TODO : Cleaner way to create job id context for execution in Ray?
        with self._component._job_id_ctx():
            job_id = DI.job_id.resolve_sync()
            self._logger = self._logger.bind(job_id=job_id)

            async with asyncio.TaskGroup() as tg:
                for conn in connectors:
                    tg.create_task(self._add_channel(conn))
            self._create_input_field_group_tasks()
            self._validate_connections()
            self._logger.info("IOController connected")

    async def _add_channel(self, connector: Connector) -> None:
        if connector.spec.source.connects_to([self.namespace]):
            chan = await connector.connect_send()
            self._add_channel_for_field(
                connector.spec.source.descriptor, connector.spec.id, IODirection.OUTPUT, chan
            )
        if connector.spec.target.connects_to([self.namespace]):
            chan = await connector.connect_recv()
            self._add_channel_for_field(
                connector.spec.target.descriptor, connector.spec.id, IODirection.INPUT, chan
            )
        if connector.spec.source.connects_to(self._output_event_types):
            chan = await connector.connect_send()
            self._add_channel_for_event(connector.spec.source.entity, IODirection.OUTPUT, chan)
        if connector.spec.target.connects_to(self._input_event_types):
            chan = await connector.connect_recv()
            self._add_channel_for_event(connector.spec.target.entity, IODirection.INPUT, chan)

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

    def _create_input_field_group_tasks(self) -> None:
        """Groups input field channels by field name and launches read tasks for group inputs."""
        if not self._has_field_inputs:
            return
        field_channels: dict[str, list[tuple[_t_field_key, Channel]]] = defaultdict(list)
        for key, chan in self._input_channels.items():
            field, _ = key
            field_channels[field].append((key, chan))
        for field, channels in field_channels.items():
            if len(channels) == 1:
                continue
            fan_in = AsyncioChannel(maxsize=100)
            self._input_channels[(field, _io_key_in)] = fan_in
            task_name = f"group:{field}"
            group_task = asyncio.create_task(
                self._read_field_group(channels, fan_in), name=task_name
            )
            self._read_tasks[task_name] = group_task

    def _validate_connections(self) -> None:
        connected_inputs = set(k for k, _ in self._input_channels.keys())
        connected_outputs = set(k for k, _ in self._output_channels.keys())
        if unconnected_inputs := set(self.inputs) - connected_inputs:
            self._logger.error(
                "Input fields not connected, process may hang", unconnected=unconnected_inputs
            )
        if unconnected_outputs := set(self.outputs) - connected_outputs:
            self._logger.warning("Output fields not connected", unconnected=unconnected_outputs)

    @cache
    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "namespace": self.namespace,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "input_events": [e.safe_type() for e in self.input_events],
            "output_events": [e.safe_type() for e in self.output_events],
            "initial_values": {k: list(v) for k, v in self._initial_values.items()},
        }


class IOBuffer(_t.Protocol):
    """`IOBuffer` is a buffer for input/output data."""

    def put(self, items: _t.Iterable) -> None:
        """Adds items to the buffer."""
        ...

    def flush(self) -> _t.Iterable:
        """Returns items in the buffer and resets the buffer."""
        ...


class IOFieldBuffer(IOBuffer):
    """`IOFieldBuffer` is a buffer for input/output data."""

    def __init__(self) -> None:
        self._buf: dict[str, _t.Any] = dict()

    def put(self, items: _t.Iterable) -> None:
        """Adds items to the buffer."""
        self._buf.update(dict(items))

    def flush(self) -> _t.Iterable:
        """Returns items in the buffer and resets the buffer."""
        items = self._buf.items()
        self._buf = dict()
        return items

    def __bool__(self) -> bool:
        return bool(self._buf)


class IOEventBuffer(IOBuffer):
    """`IOEventBuffer` is a buffer for input/output events."""

    def __init__(self) -> None:
        self._buf: deque = deque()

    def put(self, items: _t.Iterable) -> None:
        """Adds items to the buffer."""
        self._buf.extend(items)

    def flush(self) -> _t.Iterable:
        """Returns items in the buffer and resets the buffer."""
        items = self._buf
        self._buf = deque()
        return items

    def __bool__(self) -> bool:
        return bool(self._buf)
