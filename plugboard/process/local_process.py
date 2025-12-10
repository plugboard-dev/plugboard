"""Provides the `LocalProcess` class for managing components on a single processor."""

import asyncio
import typing as _t

from plugboard.component import Component
from plugboard.connector import Connector
from plugboard.process.process import Process
from plugboard.schemas import Status
from plugboard.state.state_backend import StateBackend


class LocalProcess(Process):
    """`LocalProcess` manages components in a process model on a single processor."""

    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        name: _t.Optional[str] = None,
        parameters: _t.Optional[dict[str, _t.Any]] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        """Instantiates a `LocalProcess`.

        Args:
            components: The components in the `Process`.
            connectors: The connectors between the components.
            name: Optional; Name for this `Process`.
            parameters: Optional; Parameters for the `Process`.
            state: Optional; `StateBackend` for the `Process`.
        """
        super().__init__(
            components=components,
            connectors=connectors,
            name=name,
            parameters=parameters,
            state=state,
        )
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def _connect_components(self) -> None:
        connectors = list(self.connectors.values())
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.io.connect(connectors))
        # Allow time for connections to be established
        # TODO : Replace with a more robust mechanism
        await asyncio.sleep(1)

    async def _connect_state(self) -> None:
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.connect_state(self._state))
            for connector in self.connectors.values():
                tg.create_task(self._state.upsert_connector(connector))

    async def init(self) -> None:
        """Performs component initialisation actions."""
        async with asyncio.TaskGroup() as tg:
            await self.connect_state()
            await self._connect_components()
            for component in self.components.values():
                tg.create_task(component.init())
        await super().init()
        self._logger.info("Process initialised")

    async def step(self) -> None:
        """Executes a single step for the process."""
        await super().step()
        try:
            async with asyncio.TaskGroup() as tg:
                for component in self.components.values():
                    self._tasks[component.id] = tg.create_task(component.step())
        except Exception:
            await self._set_status(Status.FAILED)
            raise
        else:
            await self._set_status(Status.WAITING)

    async def run(self) -> None:
        """Runs the process to completion."""
        await super().run()
        self._logger.info("Starting process run")
        try:
            async with asyncio.TaskGroup() as tg:
                for component in self.components.values():
                    self._tasks[component.id] = tg.create_task(component.run())
        except Exception:
            await self._set_status(Status.FAILED)
            self._remove_signal_handlers()
            raise
        else:
            if self.status == Status.RUNNING:
                await self._set_status(Status.COMPLETED)
        finally:
            self._remove_signal_handlers()
        self._logger.info("Process run complete")

    def cancel(self) -> None:
        """Cancels the process run."""
        for task in self._tasks.values():
            task.cancel()
        super().cancel()

    async def destroy(self) -> None:
        """Performs tear-down actions for the `LocalProcess` and its `Component`s."""
        async with asyncio.TaskGroup() as tg:
            for component in self.components.values():
                tg.create_task(component.destroy())
            await super().destroy()
