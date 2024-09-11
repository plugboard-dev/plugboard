"""Provides Component class."""

from abc import ABC, abstractmethod
from functools import wraps
import typing as _t

from plugboard.component.io_controller import IOController, IODirection
from plugboard.state import StateBackend
from plugboard.utils import AsDictMixin


class Component(ABC, AsDictMixin):
    """`Component` base class for all components in a process model."""

    io: IOController

    def __init__(
        self,
        name: str,
        initial_values: _t.Optional[dict] = None,
        parameters: _t.Optional[dict] = None,
        constraints: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        self.name = name
        self._initial_values = initial_values or {}
        self._constraints = constraints or {}
        self._parameters = parameters or {}
        self.state = state
        self.io = IOController(
            inputs=type(self).io.inputs, outputs=type(self).io.outputs, namespace=name
        )
        self.step = self._handle_step_wrapper()  # type: ignore

    async def init(self) -> None:
        """Performs component initialisation actions."""
        pass

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
            await self._step()
            self._bind_outputs()
            await self.io.write()

        return _wrapper

    def _bind_inputs(self) -> None:
        """Binds input fields to component fields."""
        for field in self.io.inputs:
            setattr(self, field, self.io.data[IODirection.INPUT][field])

    def _bind_outputs(self) -> None:
        """Binds component fields to output fields."""
        for field in self.io.outputs:
            self.io.data[IODirection.OUTPUT][field] = getattr(self, field)

    async def run(self) -> None:
        """Executes component logic for all steps to completion."""
        pass

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            **self.io.data,
        }
