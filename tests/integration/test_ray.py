"""Integration tests for Ray features.

TODO: Revise/remove these tests depending on multiprocessing support.
"""
# ruff: noqa: D101,D102,D103

import asyncio
import tempfile
import typing as _t

import pytest
import ray

from plugboard.connector import Connector, RayChannelBuilder
from plugboard.schemas import ConnectorSpec
from plugboard.state import RayStateBackend
from plugboard.utils import build_actor_wrapper
from tests.integration.test_process_with_components_run import A, B, C


@pytest.fixture
def temp_file_path() -> _t.Iterator[str]:
    """Returns a temporary file path."""
    with tempfile.NamedTemporaryFile(suffix=".txt") as f:
        yield f.name


ActorA = build_actor_wrapper(A)
ActorB = build_actor_wrapper(B)
ActorC = build_actor_wrapper(C)


@pytest.mark.anyio
async def test_ray_run(temp_file_path: str) -> None:
    """Basic test for some components running in Ray."""
    channel_builder = RayChannelBuilder()
    state = RayStateBackend()

    components = [
        ray.remote(num_cpus=0.1)(ActorA).remote(name="A", iters=10),  # type: ignore
        ray.remote(num_cpus=0.1)(ActorB).remote(name="B", factor=45),  # type: ignore
        ray.remote(num_cpus=0.1)(ActorC).remote(name="C", path=temp_file_path),  # type: ignore
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
    await asyncio.gather(*(component.connect_state.remote(state) for component in components))  # type: ignore
    await asyncio.gather(*(component.io_connect.remote(connectors) for component in components))  # type: ignore

    await asyncio.gather(*(component.init.remote() for component in components))  # type: ignore
    await asyncio.gather(*(component.run.remote() for component in components))  # type: ignore

    with open(temp_file_path, "r") as f:
        data = f.read()

    comp_c_outputs = [float(output) for output in data.splitlines()]
    expected_comp_c_outputs = [45 * i for i in range(10)]
    assert comp_c_outputs == expected_comp_c_outputs
