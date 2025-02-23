"""Provides Component class."""

from abc import ABC, abstractmethod
import asyncio
from functools import wraps
import typing as _t

import structlog

from plugboard.component.io_controller import (
    IOController,
    IODirection,
    IOStreamClosedError,
)
from plugboard.events import Event, EventHandlers
from plugboard.exceptions import UnrecognisedEventError
from plugboard.state import StateBackend
from plugboard.utils import ClassRegistry, ExportMixin


logger = structlog.get_logger()


class Component(ABC, ExportMixin):
    """`Component` base class for all components in a process model."""

    io: IOController

    def __init__(
        self,
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
        self.io = IOController(
            inputs=self.__class__.io.inputs,
            outputs=self.__class__.io.outputs,
            initial_values=initial_values,
            input_events=self.__class__.io.input_events,
            output_events=self.__class__.io.output_events,
            namespace=name,
        )
        self.init = self._handle_init_wrapper()  # type: ignore
        self.step = self._handle_step_wrapper()  # type: ignore
        self.logger = logger.bind(cls=self.__class__.__name__, name=self.name)
        self.logger.info("Component created")

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init_subclass__(*args, **kwargs)
        if not hasattr(cls, "io"):
            raise NotImplementedError(f"{cls.__name__} must define an `io` attribute.")
        ComponentRegistry.add(cls)

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
        if self._state_is_connected:
            return
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
        # TODO : Correct behaviour for missing fields (can happen when using events)?
        for field in self.io.inputs:
            field_default = getattr(self, field, None)
            value = self.io.data[str(IODirection.INPUT)].get(field, field_default)
            setattr(self, field, value)

    def _bind_outputs(self) -> None:
        """Binds component fields to output fields."""
        # TODO : Correct behaviour for missing fields (can happen when using events)?
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

    async def run(self) -> None:
        """Executes component logic for all steps to completion."""
        while True:
            try:
                await self.step()
            except IOStreamClosedError:
                break

    async def destroy(self) -> None:
        """Performs tear-down actions for `Component`."""
        self.logger.info("Component destroyed")

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "id": self.id,
            "name": self.name,
            **self.io.data,
        }


class ComponentRegistry(ClassRegistry[Component]):
    """A registry of all `Component` types."""

    pass
