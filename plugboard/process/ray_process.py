"""Provides the `RayProcess` class for managing components in a Ray cluster."""

import asyncio
import typing as _t

from plugboard.component import Component
from plugboard.component.io_controller import IODirection
from plugboard.connector import Connector
from plugboard.process.process import Process
from plugboard.state import RayStateBackend, StateBackend
from plugboard.utils import build_actor_wrapper, depends_on_optional, gather_except


try:
    import ray
except ImportError:
    pass


class RayProcess(Process):
    """`RayProcess` manages components in a process model on a multiple Ray actors."""

    _default_state_cls = RayStateBackend

    @depends_on_optional("ray")
    def __init__(
        self,
        components: _t.Iterable[Component],
        connectors: _t.Iterable[Connector],
        name: _t.Optional[str] = None,
        parameters: _t.Optional[dict] = None,
        state: _t.Optional[StateBackend] = None,
    ) -> None:
        """Instantiates a `RayProcess`.

        Args:
            components: The components in the `Process`.
            connectors: The connectors between the components.
            name: Optional; Name for this `Process`.
            parameters: Optional; Parameters for the `Process`.
            state: Optional; `StateBackend` for the `Process`.
        """
        self._component_actors = {
            # Recreate components on remote actors
            c.id: self._create_component_actor(c)
            for c in components
        }

        super().__init__(
            components=components,
            connectors=connectors,
            name=name,
            parameters=parameters,
            state=state,
        )

    def _create_component_actor(self, component: Component) -> _t.Any:
        name = component.id
        args = component.export()["args"]
        actor_cls = build_actor_wrapper(component.__class__)
        return ray.remote(num_cpus=0, name=name)(actor_cls).remote(**args)  # type: ignore

    async def _update_component_attributes(self) -> None:
        """Updates attributes on local components from remote actors."""
        component_ids = [c.id for c in self.components.values()]
        remote_states = await gather_except(
            *[self._component_actors[id].dict.remote() for id in component_ids]
        )
        for id, state in zip(component_ids, remote_states):
            self.components[id].__dict__.update(
                {
                    **state[str(IODirection.INPUT)],
                    **state[str(IODirection.OUTPUT)],
                    **state["exports"],
                }
            )

    async def _connect_components(self) -> None:
        connectors = list(self.connectors.values())
        connect_coros = [
            component.io_connect.remote(connectors) for component in self._component_actors.values()
        ]
        await gather_except(*connect_coros)
        # Allow time for connections to be established
        # TODO : Replace with a more robust mechanism
        await asyncio.sleep(1)

    async def _connect_state(self) -> None:
        component_coros = [
            component.connect_state.remote(self._state)
            for component in self._component_actors.values()
        ]
        connector_coros = [
            self._state.upsert_connector(connector) for connector in self.connectors.values()
        ]
        await gather_except(*component_coros, *connector_coros)

    async def init(self) -> None:
        """Performs component initialisation actions."""
        await self.connect_state()
        await self._connect_components()
        coros = [component.init.remote() for component in self._component_actors.values()]
        await gather_except(*coros)
        await self._update_component_attributes()
        await super().init()
        self._logger.info("Process initialised")

    async def step(self) -> None:
        """Executes a single step for the process."""
        coros = [component.step.remote() for component in self._component_actors.values()]
        await gather_except(*coros)
        await self._update_component_attributes()

    async def run(self) -> None:
        """Runs the process to completion."""
        await super().run()
        self._logger.info("Starting process run")
        coros = [component.run.remote() for component in self._component_actors.values()]
        await gather_except(*coros)
        await self._update_component_attributes()
        self._logger.info("Process run complete")

    async def destroy(self) -> None:
        """Performs tear-down actions for the `RayProcess` and its `Component`s."""
        coros = [component.destroy.remote() for component in self._component_actors.values()]
        await gather_except(*coros)
        await super().destroy()
