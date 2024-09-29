"""Provides the `Process` class for managing components in a process model."""

import asyncio
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
        self.components: dict[str, Component] = {c.name: c for c in components}
        self.connectors: list[Connector] = list(connectors)
        self.parameters: dict = parameters or {}
        self.state: StateBackend = state or DictStateBackend()
        self._connect_components()

    @property
    def id(self) -> str:
        """Unique ID for `Process`."""
        return self.name

    def _connect_components(self) -> None:
        for component in self.components.values():
            component.io.connect(self.connectors)

    async def init(self) -> None:
        """Performs component initialisation actions."""
        async with asyncio.TaskGroup() as tg:
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
