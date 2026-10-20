"""Provides the `RayProcess` class for managing components in a Ray cluster."""

import asyncio
import sys
import typing as _t

from plugboard.component import Component
from plugboard.component.io_controller import IODirection
from plugboard.connector import Connector
from plugboard.process.process import Process
from plugboard.schemas import Resource, Status
from plugboard.state import RayStateBackend, StateBackend
from plugboard.utils import build_actor_wrapper, depends_on_optional, gen_rand_str


try:
    import ray
except ImportError:  # pragma: no cover
    pass


_ATTRIBUTE_UPDATE_TIMEOUT_SECONDS = 5.0


async def _gather[T](*awaitables: _t.Awaitable[T]) -> list[T]:
    """Gather Ray references and local awaitables, cancelling siblings on failure.

    ObjectRefs are awaitable but are not coroutines accepted by TaskGroup.
    Cancelling their local waits does not cancel the remote calls, so explicitly
    cancel submitted references when the group fails or its caller is cancelled.
    """

    async def _await(awaitable: _t.Awaitable[T]) -> T:
        return await awaitable

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(_await(awaitable)) for awaitable in awaitables]
    except BaseException:
        for awaitable in awaitables:
            if isinstance(awaitable, ray.ObjectRef):
                ray.cancel(awaitable)
        raise
    return [task.result() for task in tasks]


class RayProcess(Process):
    """Manages components on multiple Ray actors.

    Concurrent lifecycle calls use TaskGroup: a failure cancels sibling local
    waits, requests cancellation of remote calls, and raises an ExceptionGroup.
    Remote cancellation is cooperative and may still be in progress on return.
    """

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
        # TODO: Replace with a namespace based on the job ID or similar
        self._namespace = f"plugboard-{gen_rand_str(16)}"
        self._component_actors = {
            # Recreate components on remote actors
            c.id: self._create_component_actor(c)
            for c in components
        }
        self._tasks: dict[str, ray.ObjectRef] = {}

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

        # Get resource requirements from component
        resources = component.resources
        if resources is None:
            # Use default resources if not specified
            resources = Resource()

        ray_options = resources.to_ray_options()
        ray_options["name"] = name
        ray_options["namespace"] = self._namespace

        return ray.remote(**ray_options)(actor_cls).remote(**args)  # type: ignore

    async def _update_component_attributes(self, *, best_effort: bool = False) -> None:
        """Updates local attributes, bounding refreshes while propagating a failure."""
        component_ids = [c.id for c in self.components.values()]
        try:
            timeout = _ATTRIBUTE_UPDATE_TIMEOUT_SECONDS if best_effort else None
            async with asyncio.timeout(timeout):
                remote_states = await _gather(
                    *[self._component_actors[id].dict.remote() for id in component_ids]
                )
        except Exception:
            if not best_effort:
                raise
            self._logger.warning(
                "Could not refresh component attributes after failure", exc_info=True
            )
            return
        for id, state in zip(component_ids, remote_states):
            self.components[id].__dict__.update(
                {
                    **state[str(IODirection.INPUT)],
                    **state[str(IODirection.OUTPUT)],
                    **state["exports"],
                    "_status": state["status"],
                }
            )

    async def _connect_components(self) -> None:
        connectors = list(self.connectors.values())
        connect_coros = [
            component.io_connect.remote(connectors) for component in self._component_actors.values()
        ]
        await _gather(*connect_coros)
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
        await _gather(*component_coros, *connector_coros)

    async def init(self) -> None:
        """Performs component initialisation actions."""
        await self.connect_state()
        await self._connect_components()
        coros = [component.init.remote() for component in self._component_actors.values()]
        try:
            await _gather(*coros)
        finally:
            await self._update_component_attributes(best_effort=sys.exception() is not None)
        await super().init()
        self._logger.info("Process initialised")

    async def step(self) -> None:
        """Executes a single step for the process."""
        await super().step()
        coros = [component.step.remote() for component in self._component_actors.values()]
        try:
            await _gather(*coros)
        except Exception:
            await self._set_status(Status.FAILED)
            raise
        else:
            await self._set_status(Status.WAITING)
        finally:
            await self._update_component_attributes(best_effort=sys.exception() is not None)

    async def run(self) -> None:
        """Runs the process to completion."""
        await super().run()
        self._logger.info("Starting process run")
        coros = [component.run.remote() for component in self._component_actors.values()]
        try:
            self._tasks = {comp.id: ref for comp, ref in zip(self.components.values(), coros)}
            await _gather(*coros)
        except* ray.exceptions.TaskCancelledError:
            # Ray tasks were cancelled, now call cancel on components to update status
            await _gather(
                *[component.cancel.remote() for component in self._component_actors.values()]
            )
        except* Exception:
            await self._set_status(Status.FAILED)
            raise
        else:
            if self.status == Status.RUNNING:
                await self._set_status(Status.COMPLETED)
        finally:
            self._remove_signal_handlers()
            await self._update_component_attributes(best_effort=sys.exception() is not None)
        self._logger.info("Process run complete")

    def cancel(self) -> None:
        """Cancels the process run."""
        for task in self._tasks.values():
            ray.cancel(task)
        super().cancel()

    async def destroy(self) -> None:
        """Performs tear-down actions for the `RayProcess` and its `Component`s."""
        coros = [component.destroy.remote() for component in self._component_actors.values()]
        await _gather(*coros)
        await super().destroy()
