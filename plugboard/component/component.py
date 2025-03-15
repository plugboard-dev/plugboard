"""Provides Component class."""

from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict
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
        parent_comps = [c for c in cls.__bases__ if issubclass(c, Component)]
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

    # Prevents type-checker errors on public component IO attributes
    def __getattr__(self, key: str) -> _t.Any:
        if not key.startswith("_"):
            return None
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

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

    def _handle_step_wrapper(self) -> _t.Callable:
        self._step = self.step

        @wraps(self.step)
        async def _wrapper() -> None:
            await self.io.read()
            self._bind_inputs()
            await self._handle_events()
            await self._step()
            self._bind_outputs()
            await self.io.write()

        return _wrapper

    def _bind_inputs(self) -> None:
        """Binds input fields to component fields."""
        for field in self.io.inputs:
            field_default = getattr(self, field, None)
            value = self.io.data[str(IODirection.INPUT)].get(field, field_default)
            setattr(self, field, value)

    def _bind_outputs(self) -> None:
        """Binds component fields to output fields."""
        for field in self.io.outputs:
            field_default = getattr(self, field, None)
            self.io.data[str(IODirection.OUTPUT)][field] = field_default

    async def _handle_events(self) -> None:
        """Handles incoming events."""
        async with asyncio.TaskGroup() as tg:
            while self.io.events[str(IODirection.INPUT)]:
                event = self.io.events[str(IODirection.INPUT)].popleft()
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
        return {
            "id": self.id,
            "name": self.name,
            **self.io.data,
            "exports": {name: getattr(self, name, None) for name in self.exports or []},
        }


class ComponentRegistry(ClassRegistry[Component]):
    """A registry of all `Component` types."""

    pass
