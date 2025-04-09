"""Provides Component class."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict, deque
from functools import wraps
import typing as _t

from plugboard.component.io_controller import IOController as IO, IODirection
from plugboard.events import Event, EventHandlers, StopEvent
from plugboard.exceptions import (
    IOSetupError,
    IOStreamClosedError,
    UnrecognisedEventError,
    ValidationError,
)
from plugboard.state import StateBackend
from plugboard.utils import DI, ClassRegistry, ExportMixin, is_on_ray_worker


_io_key_in: str = str(IODirection.INPUT)
_io_key_out: str = str(IODirection.OUTPUT)


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
        )
        self._field_inputs: dict[str, _t.Any] = {}
        self._field_inputs_ready: bool = False

        self._logger = DI.logger.sync_resolve().bind(cls=self.__class__.__name__, name=self.name)
        self._logger.info("Component created")

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init_subclass__(*args, **kwargs)
        if is_on_ray_worker():
            # Required until https://github.com/ray-project/ray/issues/42823 is resolved
            return
        ComponentRegistry.add(cls)
        # Configure IO last in case it fails in case of components with dynamic io args
        cls._configure_io()

    @classmethod
    def _configure_io(cls) -> None:
        # Get all parent classes that are Component subclasses
        parent_comps = cls._get_component_bases()
        # Create combined set of all io arguments from this class and all parents
        io_args: dict[str, set] = defaultdict(set)
        for c in parent_comps + [cls]:
            if {c_io := getattr(c, "io")}:
                io_args["inputs"].update(c_io.inputs)
                io_args["outputs"].update(c_io.outputs)
                io_args["input_events"].update(c_io.input_events)
                io_args["output_events"].update(c_io.output_events)
        # Set io arguments for subclass
        cls.io = IO(
            inputs=sorted(io_args["inputs"], key=str),
            outputs=sorted(io_args["outputs"], key=str),
            input_events=sorted(io_args["input_events"], key=str),
            output_events=sorted(io_args["output_events"], key=str),
        )
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
        await self._state.upsert_component(self)
        self._state_is_connected = True

    async def init(self) -> None:
        """Performs component initialisation actions."""
        pass

    def _handle_init_wrapper(self) -> _t.Callable:
        self._init = self.init

        @wraps(self.init)
        async def _wrapper() -> None:
            await self._init()
            if self._state is not None and self._state_is_connected:
                await self._state.upsert_component(self)

        return _wrapper

    @abstractmethod
    async def step(self) -> None:
        """Executes component logic for a single step."""
        pass

    @property
    def _can_step(self) -> bool:
        """Checks if the component can step.

        - if a component has no input or output fields, it cannot step (purely event-driven case);
        - if a component requires inputs, it can only step if all the inputs are available;
        - otherwise, a component which has outputs but does not require inputs can always step.
        """
        consumes_no_inputs = len(self.io.inputs) == 0
        produces_no_outputs = len(self.io.outputs) == 0
        if consumes_no_inputs and produces_no_outputs:
            return False
        return consumes_no_inputs or self._field_inputs_ready

    def _handle_step_wrapper(self) -> _t.Callable:
        self._step = self.step

        @wraps(self.step)
        async def _wrapper() -> None:
            await self.io.read()
            await self._handle_events()
            self._bind_inputs()
            if self._can_step:
                await self._step()
            self._bind_outputs()
            await self.io.write()
            self._field_inputs_ready = False

        return _wrapper

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

    async def run(self) -> None:
        """Executes component logic for all steps to completion."""
        while True:
            try:
                await self.step()
            except IOStreamClosedError:
                break

    async def destroy(self) -> None:
        """Performs tear-down actions for `Component`."""
        self._logger.info("Component destroyed")

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        field_data = {
            _io_key_in: {k: getattr(self, k, None) for k in self.io.inputs},
            _io_key_out: {k: getattr(self, k, None) for k in self.io.outputs},
        }
        return {
            "id": self.id,
            "name": self.name,
            **field_data,
            "exports": {name: getattr(self, name, None) for name in self.exports or []},
        }


class ComponentRegistry(ClassRegistry[Component]):
    """A registry of all `Component` types."""

    pass
