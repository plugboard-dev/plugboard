"""Provides Component class."""

from __future__ import annotations

from abc import ABC
import asyncio
from collections import defaultdict, deque
from functools import cached_property, wraps
import typing as _t

from that_depends import ContextScopes, container_context

from plugboard.component.io_controller import IOController as IO, IODirection
from plugboard.events import Event, EventHandlers, StopEvent
from plugboard.exceptions import (
    EventStreamClosedError,
    IOSetupError,
    IOStreamClosedError,
    ProcessStatusError,
    UnrecognisedEventError,
    ValidationError,
)
from plugboard.schemas.state import Status
from plugboard.state import StateBackend
from plugboard.utils import DI, ClassRegistry, ExportMixin, is_on_ray_worker


_io_key_in: str = str(IODirection.INPUT)
_io_key_out: str = str(IODirection.OUTPUT)

# Component IO read timeout in seconds
# Read timeout from env var with default as this is simplest way to patch in tests
IO_READ_TIMEOUT_SECONDS = DI.settings.resolve_sync().io_read_timeout or 20.0


class Component(ABC, ExportMixin):
    """`Component` base class for all components in a process model.

    Attributes:
        name: The name of the component.
        io: The `IOController` for the component, specifying inputs, outputs, and events.
        exports: Optional; The exportable fields from the component during distributed runs
            in addition to input and output fields.
    """

    io: IO = IO(input_events=[StopEvent], output_events=[StopEvent])
    exports: _t.Optional[list[str]] = None

    _implements_step: bool = False

    def __init__(
        self,
        *,
        name: str,
        initial_values: _t.Optional[dict[str, _t.Iterable]] = None,
        parameters: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
        constraints: _t.Optional[dict] = None,
    ) -> None:
        self.name = name
        self._initial_values = initial_values or {}
        self._constraints = constraints or {}
        self._parameters = parameters or {}
        self._state: _t.Optional[StateBackend] = state
        self._state_is_connected = False

        setattr(self, "init", self._handle_init_wrapper())
        setattr(self, "step", self._handle_step_wrapper())

        if is_on_ray_worker():
            # Required until https://github.com/ray-project/ray/issues/42823 is resolved
            try:
                self.__class__._configure_io()
            except IOSetupError:
                pass
        self.io = IO(
            inputs=self.__class__.io.inputs,
            outputs=self.__class__.io.outputs,
            initial_values=self._initial_values,
            input_events=self.__class__.io.input_events,
            output_events=self.__class__.io.output_events,
            namespace=self.name,
            component=self,
        )
        self._event_producers: dict[str, set[str]] = defaultdict(set)
        self._status = Status.CREATED
        self._is_running = False
        self._field_inputs: dict[str, _t.Any] = {}
        self._field_inputs_ready: bool = False

        self._logger = DI.logger.resolve_sync().bind(cls=self.__class__.__name__, name=self.name)
        self._logger.info("Component created")

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init_subclass__(*args, **kwargs)
        if is_on_ray_worker():
            # Required until https://github.com/ray-project/ray/issues/42823 is resolved
            return
        ComponentRegistry.add(cls)
        # Configure IO last in case it fails in case of components with dynamic io args
        cls._configure_io()

    async def _set_status(self, status: Status, publish: bool = True) -> None:
        """Sets the status of the component and optionaly publishes it to the state backend."""
        self._status = status
        if publish and self._state and self._state_is_connected:
            await self._state.upsert_component(self)

    @property
    def status(self) -> Status:
        """Gets the status of the component."""
        return self._status

    @classmethod
    def _configure_io(cls) -> None:
        # Get all parent classes that are Component subclasses
        parent_comps = cls._get_component_bases()
        # Create combined set of all io arguments from this class and all parents
        io_args: dict[str, set] = defaultdict(set)
        exports: list[str] = []
        for c in parent_comps + [cls]:
            if c_io := getattr(c, "io"):
                io_args["inputs"].update(c_io.inputs)
                io_args["outputs"].update(c_io.outputs)
                io_args["input_events"].update(c_io.input_events)
                io_args["output_events"].update(c_io.output_events)
            if c_exports := getattr(c, "exports"):
                exports.extend(c_exports)
        # Set io arguments for subclass
        cls.io = IO(
            inputs=sorted(io_args["inputs"], key=str),
            outputs=sorted(io_args["outputs"], key=str),
            input_events=sorted(io_args["input_events"], key=str),
            output_events=sorted(io_args["output_events"], key=str),
        )
        # Set exports for subclass
        cls.exports = sorted(set(exports))
        # Check that subclass io arguments is superset of abstract base class Component io arguments
        # Note: can't check cls.__abstractmethods__ as it's unset at this point. Maybe brittle...
        cls_is_concrete = ABC not in cls.__bases__
        extends_base_io_args = (
            io_args["inputs"] > set(Component.io.inputs)
            or io_args["outputs"] > set(Component.io.outputs)
            or io_args["input_events"] > set(Component.io.input_events)
            or io_args["output_events"] > set(Component.io.output_events)
        )
        if cls_is_concrete and not extends_base_io_args:
            raise IOSetupError(
                f"{cls.__name__} must extend Component abstract base class io arguments"
            )
        # Check if component implements step method
        cls._implements_step = cls.step is not Component.step

    @classmethod
    def _get_component_bases(cls) -> list[_t.Type[Component]]:
        bases = []
        for base in cls.__bases__:
            if issubclass(base, Component):
                bases.append(base)
                bases.extend(base._get_component_bases())
        return bases

    # Prevents type-checker errors on public component IO attributes
    def __getattr__(self, key: str) -> _t.Any:
        if not key.startswith("_"):
            return None
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

    def __setattr__(self, key: str, value: _t.Any) -> None:
        """Sets attributes on the component.

        If the attribute is an input field, it is set in the field input buffer for the current
        step. This data is consumed by the `step` method when it is called and must be reset for
        subsequent steps.
        """
        if key in self.io.inputs:
            self._field_inputs[key] = value
        super().__setattr__(key, value)

    @property
    def id(self) -> str:
        """Unique ID for `Component`."""
        return self.name

    @property
    def state(self) -> _t.Optional[StateBackend]:
        """State backend for the process."""
        return self._state

    def _job_id_ctx(self) -> container_context:
        """Sets job ID context from state backend.

        Required for all Component entry points to ensure job ID is available when
        executing on Ray workers. As Ray remote function calls are executed in
        separate asyncio.Tasks, and ContextVars are local to asyncio.Tasks, the
        job ID context must be set for each remote function call.
        """
        job_id = self._state.job_id if self._state else None
        cm = container_context(
            DI,
            global_context={"job_id": job_id},
            scope=ContextScopes.APP,
            preserve_global_context=True,
        )
        with cm:
            self._logger = self._logger.bind(job_id=job_id)
        return cm

    async def connect_state(self, state: _t.Optional[StateBackend] = None) -> None:
        """Connects the `Component` to the `StateBackend`."""
        try:
            if self._state_is_connected:
                return
        except AttributeError as e:
            raise ValidationError(
                "Component invalid: did you forget to call super().__init__ in the constructor?"
            ) from e
        self._state = state or self._state
        if self._state is None:
            return
        with self._job_id_ctx():
            await self._state.upsert_component(self)
            self._state_is_connected = True

    async def init(self) -> None:
        """Performs component initialisation actions."""
        pass

    def _handle_init_wrapper(self) -> _t.Callable:
        self._init = self.init

        @wraps(self.init)
        async def _wrapper() -> None:
            with self._job_id_ctx():
                await self._build_producer_graph()
                await self._init()
                await self._set_status(Status.INIT)

        return _wrapper

    async def _build_producer_graph(self) -> None:
        """Builds the producer graph for the component."""
        if not (self._state and self._state_is_connected):
            self._logger.warning(
                "State backend not connected. Cannot build producer graph. "
                "Purely event driven models may hang indefinitely."
            )
            return
        process = await self._state.get_process_for_component(self.id)
        input_event_set = {evt.safe_type() for evt in self.io.input_events}
        input_event_set.remove(StopEvent.safe_type())
        for comp_id, comp_data in process["components"].items():
            for evt in input_event_set.intersection(comp_data["io"]["output_events"]):
                if comp_id == self.id:
                    # TODO : How to handle the case of recursion, i.e., a component which is both
                    #      : a producer and consumer of a given event?
                    continue  # Skip self to avoid indefinite hanging
                self._event_producers[evt].add(comp_id)

    async def _update_producer_graph(self) -> None:
        """Updates the producer graph for the component."""
        if not (self._state and self._state_is_connected):
            self._logger.warning("State backend not connected. Cannot update producer graph.")
            return
        if not self._event_producers:
            return  # Nothing to do
        process = await self._state.get_process_for_component(self.id)
        for evt in list(self._event_producers.keys()):
            for comp_id in list(self._event_producers[evt]):
                comp_status = process["components"][comp_id]["status"]
                if comp_status not in (Status.RUNNING, Status.WAITING):
                    self._event_producers[evt].remove(comp_id)
            if not self._event_producers[evt]:
                self._event_producers.pop(evt)
        if not self._event_producers:
            raise EventStreamClosedError("No more events to process.")

    async def step(self) -> None:
        """Executes component logic for a single step."""
        raise NotImplementedError("Component step method not implemented")

    @cached_property
    def _produces_no_output_events(self) -> bool:
        output_events = set([evt.safe_type() for evt in self.io.output_events])
        return len(output_events - {StopEvent.safe_type()}) == 0

    @property
    def _can_step(self) -> bool:
        """Checks if the component can step.

        The rules for whether a component can step are as follows:
        - if a component does not implement the `step` method, it cannot step;
        - if a component produces no outputs and consumes no input fields, it cannot step (purely
          event-driven case);
        - if a component requires inputs, it can only step if all the inputs are available;
        - otherwise, a component which has outputs but does not require inputs can always step.
        """
        if not self._implements_step:
            return False
        produces_no_outputs = self._produces_no_output_events and len(self.io.outputs) == 0
        consumes_no_input_fields = len(self.io.inputs) == 0
        if consumes_no_input_fields and produces_no_outputs:
            return False
        return consumes_no_input_fields or self._field_inputs_ready

    def _handle_step_wrapper(self) -> _t.Callable:
        self._step = self.step

        @wraps(self.step)
        async def _wrapper() -> None:
            with self._job_id_ctx():
                await self._set_status(Status.RUNNING, publish=not self._is_running)
                await self._io_read_with_status_check()
                await self._handle_events()
                self._bind_inputs()
                if self._can_step:
                    try:
                        await self._step()
                    except Exception as e:
                        await self._set_status(Status.FAILED)
                        self._logger.exception("Component step failed")
                        raise e
                self._bind_outputs()
                await self.io.write()
                self._field_inputs_ready = False
                await self._set_status(Status.WAITING, publish=not self._is_running)

        return _wrapper

    @cached_property
    def _has_field_inputs(self) -> bool:
        return len(self.io.inputs) > 0

    @cached_property
    def _has_event_inputs(self) -> bool:
        input_events = set([evt.safe_type() for evt in self.io.input_events])
        return len(input_events - {StopEvent.safe_type()}) > 0

    @cached_property
    def _has_inputs(self) -> bool:
        return self._has_field_inputs or self._has_event_inputs

    @cached_property
    def _has_field_outputs(self) -> bool:
        return len(self.io.outputs) > 0

    @cached_property
    def _has_event_outputs(self) -> bool:
        output_events = set([evt.safe_type() for evt in self.io.output_events])
        return len(output_events - {StopEvent.safe_type()}) > 0

    @cached_property
    def _has_outputs(self) -> bool:
        return self._has_field_outputs or self._has_event_outputs

    async def _io_read_with_status_check(self) -> None:
        """Reads from IO controller with concurrent periodic status checks.

        Status checks are performed periodically until the read completes. If the process is in a
        failed state, the component status is set to `STOPPED` and a `ProcessStatusError` is raised;
        otherwise another read attempt is made.
        """
        read_timeout = 1e-3 if self._has_outputs and not self._has_inputs else None
        done, pending = await asyncio.wait(
            (
                asyncio.create_task(self._periodic_status_check()),
                asyncio.create_task(self.io.read(timeout=read_timeout)),
            ),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if isinstance(exc, EventStreamClosedError) and len(self.io.inputs) == 0:
                await self.io.close()  # Call close for final wait and flush event buffer
            elif exc is not None:
                raise exc

    async def _periodic_status_check(self) -> None:
        """Periodically checks the status of the process and updates the component status."""
        while True:
            await asyncio.sleep(IO_READ_TIMEOUT_SECONDS)
            await self._status_check()
            # TODO : Eventually producer graph update will be event driven. For now,
            #      : the update is performed periodically, so it's called here along
            #      : with the status check.
            if len(self.io.inputs) == 0:
                await self._update_producer_graph()

    async def _status_check(self) -> None:
        """Checks the status of the process and updates the component status."""
        if not (self._state and self._state_is_connected):
            self._logger.warning("State backend not connected, skipping status check")
            return
        process_status = await self._state.get_process_status_for_component(self.id)
        self._logger.info(f"Process status for component {self.id}: {process_status}")
        if process_status == Status.FAILED:
            await self._set_status(Status.STOPPED)
            self._logger.exception("Process in failed state")
            raise ProcessStatusError(f"Process in failed state for component {self.id}")

    def _bind_inputs(self) -> None:
        """Binds input fields to component fields.

        Input binding follows these rules:
        - first, input field values are set to values assigned directly to the component;
        - then, input field values are updated with any values present in the input buffer;
        - if all inputs fields have values set through these mechanisms the component can step;
        - any input fields not set through these mechanisms are set with default values.
        """
        # TODO : Support for default input field values?
        # Consume input data directly assigned and read from channels and reset to empty values
        received_inputs = dict(self.io.buf_fields[_io_key_in].flush())
        self._field_inputs.update(received_inputs)
        # Check if all input fields have been set
        self._field_inputs_ready = all(k in self._field_inputs for k in self.io.inputs)
        for field in self.io.inputs:
            field_default = getattr(self, field, None)
            value = self._field_inputs.get(field, field_default)
            setattr(self, field, value)
        self._field_inputs = {}

    def _bind_outputs(self) -> None:
        """Binds component fields to output fields."""
        output_data = {}
        for field in self.io.outputs:
            field_default = getattr(self, field, None)
            output_data[field] = field_default
        if self._can_step:
            self.io.buf_fields[_io_key_out].put(output_data.items())

    async def _handle_events(self) -> None:
        """Handles incoming events."""
        async with asyncio.TaskGroup() as tg:
            # FIXME : If a StopEvent is received, processing of other events may hit
            #       : IOStreamClosedError due to concurrent execution.
            event_queue = deque(self.io.buf_events[_io_key_in].flush())
            while event_queue:
                event = event_queue.popleft()
                tg.create_task(self._handle_event(event))

    async def _handle_event(self, event: Event) -> None:
        """Handles an event."""
        try:
            handler = EventHandlers.get(self.__class__, event)
        except KeyError as e:
            raise UnrecognisedEventError(
                f"Unrecognised event type '{event.type}' for component '{self.__class__.__name__}'"
            ) from e
        res = await handler(self, event)
        if isinstance(res, Event):
            self.io.queue_event(res)

    @StopEvent.handler
    async def _stop_event_handler(self, event: StopEvent) -> None:
        """Stops the component on receiving the system `StopEvent`."""
        try:
            self.io.queue_event(event)
            await self.io.close()
        except IOStreamClosedError:
            pass
        await self._set_status(Status.STOPPED)

    async def run(self) -> None:
        """Executes component logic for all steps to completion."""
        self._is_running = True
        await self._set_status(Status.RUNNING)
        try:
            while True:
                try:
                    await self.step()
                except IOStreamClosedError:
                    break
            if self.status not in {Status.STOPPED, Status.FAILED}:
                await self._set_status(Status.COMPLETED)
        finally:
            self._is_running = False

    async def destroy(self) -> None:
        """Performs tear-down actions for `Component`."""
        self._state = None
        self._state_is_connected = False
        self._logger.info("Component destroyed")

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        field_data = {
            _io_key_in: {k: getattr(self, k, None) for k in self.io.inputs},
            _io_key_out: {k: getattr(self, k, None) for k in self.io.outputs},
        }
        return {
            "id": self.id,
            "name": self.name,
            "status": str(self.status),
            **field_data,
            "exports": {name: getattr(self, name, None) for name in self.exports or []},
            "io": self.io.dict(),
        }


class ComponentRegistry(ClassRegistry[Component]):
    """A registry of all `Component` types."""

    pass
