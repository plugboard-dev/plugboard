"""Provides the `Process` class for managing components in a process model."""

import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.state_backend import StateBackend
from plugboard.utils import AsDictMixin


class Process(AsDictMixin):
    """`Process` manages components in a process model."""

    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        parameters: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        self.components: dict[str, Component] = {c.name: c for c in components}
        self.connectors: list[Connector] = list(connectors)
        self.parameters: dict = parameters or {}
        self.state: StateBackend = state or StateBackend()

    async def init(self) -> None:
        """Performs component initialisation actions."""
        for component in self.components.values():
            await component.init()

    async def step(self) -> None:
        """Executes a single step for the process."""
        for component in self.components.values():
            await component.step()

    async def run(self) -> None:
        """Runs the process to completion."""
        for component in self.components.values():
            await component.run()

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            **super().dict(),
            "components": {name: component.dict() for name, component in self.components.items()},
            "connectors": [connector.dict() for connector in self.connectors],
            "parameters": self.parameters,
        }
