"""Integration tests for Ray features.

TODO: Revise/remove these tests depending on multiprocessing support.
"""
# ruff: noqa: D101,D102,D103

import asyncio
import tempfile
import typing as _t

import pytest
import ray

from plugboard.component import Component
from plugboard.connector import Connector, RayChannelBuilder
from plugboard.schemas import ConnectorSpec
from plugboard.state import RayStateBackend, StateBackend
from tests.integration.test_process_with_components_run import A, B, C


@pytest.fixture
def temp_file_path() -> _t.Iterator[str]:
    """Returns a temporary file path."""
    with tempfile.NamedTemporaryFile(suffix=".txt") as f:
        yield f.name


# TODO: Replace with a `build_actor_wrapper` class
class ComponentActor:
    def __init__(self, component_cls: type[Component], *args: _t.Any, **kwargs: _t.Any) -> None:
        self._component = component_cls(*args, **kwargs)

    async def connect_state(self, state: _t.Optional[StateBackend] = None) -> None:
        await self._component.connect_state(state)

    def connect(self, connectors: _t.Dict[str, Connector]) -> None:
        self._component.io.connect(connectors)

    async def init(self) -> None:
        await self._component.init()

    async def step(self) -> None:
        await self._component.step()

    async def run(self) -> None:
        await self._component.run()

    async def destroy(self) -> None:
        """Performs tear-down actions for `Component`."""
        await self._component.destroy()

    def getattr(self, name: str) -> _t.Any:
        """Returns attributes from the channel."""
        return getattr(self._channel, name)


@pytest.mark.anyio
async def test_ray_run(temp_file_path: str) -> None:
    """Basic test for some components running in Ray."""
    channel_builder = RayChannelBuilder()
    state = RayStateBackend()

    components = [
        ray.remote(num_cpus=0.1)(ComponentActor).remote(A, name="A", iters=10),
        ray.remote(num_cpus=0.1)(ComponentActor).remote(B, name="B", factor=45),
        ray.remote(num_cpus=0.1)(ComponentActor).remote(C, name="C", path=temp_file_path),
    ]
    connectors = [
        Connector(
            spec=ConnectorSpec(source="A.out_1", target="B.in_1"), channel=channel_builder.build()
        ),
        Connector(
            spec=ConnectorSpec(source="B.out_1", target="C.in_1"), channel=channel_builder.build()
        ),
    ]

    await state.init()
    # Task groups are not supported in Ray
    await asyncio.gather(*[state.upsert_connector(connector) for connector in connectors])
    await asyncio.gather(*(component.connect_state.remote(state) for component in components))
    await asyncio.gather(*(component.connect.remote(connectors) for component in components))

    await asyncio.gather(*(component.init.remote() for component in components))
    await asyncio.gather(*(component.run.remote() for component in components))

    with open(temp_file_path, "r") as f:
        data = f.read()

    comp_c_outputs = [float(output) for output in data.splitlines()]
    expected_comp_c_outputs = [45 * i for i in range(10)]
    assert comp_c_outputs == expected_comp_c_outputs
