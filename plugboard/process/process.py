"""Provides Process base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from types import TracebackType
import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.state import DictStateBackend, StateBackend
from plugboard.utils import ExportMixin, gen_rand_str


class Process(ExportMixin, ABC):
    """`Process` is a base class for managing components in a model."""

    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        name: _t.Optional[str] = None,
        parameters: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        self.name = name or f"{self.__class__.__name__}_{gen_rand_str(8)}"
        self.components: dict[str, Component] = {c.id: c for c in components}
        self.connectors: dict[str, Connector] = {c.id: c for c in connectors}
        self.parameters: dict = parameters or {}
        self._state: StateBackend = state or DictStateBackend()
        self._state_is_connected: bool = False
        self._connect_components()

    @property
    def id(self) -> str:
        """Unique ID for `Process`."""
        return self.name

    @property
    def state(self) -> StateBackend:
        """State backend for the process."""
        return self._state

    async def connect_state(self, state: _t.Optional[StateBackend] = None) -> None:
        """Connects the `Process` to the `StateBackend`."""
        if self._state_is_connected:
            return
        self._state = state or self._state
        if self._state is None:
            return
        async with asyncio.TaskGroup() as tg:
            await self._state.init()
            await self._state.upsert_process(self)
            for component in self.components.values():
                tg.create_task(component.connect_state(self._state))
            for connector in self.connectors.values():
                tg.create_task(self._state.upsert_connector(connector))
        self._state_is_connected = True

    @abstractmethod
    def _connect_components(self) -> None:
        """Connect components."""
        pass

    @abstractmethod
    async def init(self) -> None:
        """Performs component initialisation actions."""
        pass

    @abstractmethod
    async def step(self) -> None:
        """Executes a single step for the process."""
        pass

    @abstractmethod
    async def run(self) -> None:
        """Runs the process to completion."""
        pass

    @abstractmethod
    async def destroy(self) -> None:
        """Performs tear-down actions for the `Process` and its `Component`s."""
        pass

    async def __aenter__(self) -> Process:
        """Enters the context manager."""
        await self.init()
        return self

    async def __aexit__(
        self,
        exc_type: _t.Optional[_t.Type[BaseException]],
        exc_value: _t.Optional[BaseException],
        traceback: _t.Optional[TracebackType],
    ) -> None:
        """Exits the context manager."""
        await self.destroy()

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "id": self.id,
            "name": self.name,
            "components": {k: v.dict() for k, v in self.components.items()},
            "connectors": {k: v.dict() for k, v in self.connectors.items()},
            "parameters": self.parameters,
        }
