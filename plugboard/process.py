"""Provides the `Process` class for managing components in a process model."""

import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.state_backend import StateBackend


class Process:
    """`Process` manages components in a process model."""

    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        parameters: dict,
        state: StateBackend,
    ) -> None:
        self.components: dict[str, Component] = {c.name: c for c in components}
        self.connectors: list[Connector] = list(connectors)
        self.parameters: dict = parameters
        self.state: StateBackend = state

    async def init(self) -> None:
        """Performs component initialisation actions."""
        pass

    async def step(self) -> None:
        """Executes a single step for the process."""
        pass

    async def run(self) -> None:
        """Runs the process to completion."""
        pass
