"""Provides the `LocalProcess` class for managing components on a single processor."""

import asyncio

from plugboard.process.process import Process


class LocalProcess(Process):
    """`LocalProcess` manages components in a process model on a single processor."""

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
        """Performs tear-down actions for the `LocalProcess` and its `Component`s."""
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.destroy())
            await self._state.destroy()
