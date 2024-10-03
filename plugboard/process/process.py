"""Provides the `Process` class for managing components in a process model."""

from __future__ import annotations

import asyncio
from types import TracebackType
import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.state import DictStateBackend, StateBackend
from plugboard.utils import AsDictMixin, gen_rand_str


class Process(AsDictMixin):
    """`Process` manages components in a process model."""

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
        """Connects the `Process` to the StateBackend."""
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

    def _connect_components(self) -> None:
        connectors = list(self.connectors.values())
        for component in self.components.values():
            component.io.connect(connectors)

    async def init(self) -> None:
        """Performs component initialisation actions."""
        async with asyncio.TaskGroup() as tg:
            await self.connect_state()
            for component in self.components.values():
                tg.create_task(component.init())

    async def step(self) -> None:
        """Executes a single step for the process."""
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.step())

    async def run(self) -> None:
        """Runs the process to completion."""
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.run())

    async def destroy(self) -> None:
        """Performs tear-down actions for the `Process` and its `Component`s."""
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.destroy())
            await self._state.destroy()

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
            "name": self.name,
            "components": {k: v.dict() for k, v in self.components.items()},
            "connectors": {k: v.dict() for k, v in self.connectors.items()},
            "parameters": self.parameters,
        }
