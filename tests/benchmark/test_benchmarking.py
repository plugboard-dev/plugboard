"""Benchmark tests for Plugboard processes."""

import pytest
from pytest_codspeed import BenchmarkFixture
import uvloop

from plugboard.connector import AsyncioConnector, Connector, RayConnector, ZMQConnector
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ConnectorSpec
from tests.integration.test_process_with_components_run import A, B


ITERS = 1000

CONNECTOR_PROCESS_PARAMS = [
    (AsyncioConnector, LocalProcess),
    (ZMQConnector, LocalProcess),
    (RayConnector, RayProcess),
]
CONNECTOR_PROCESS_IDS = ["asyncio", "zmq", "ray"]


def _build_process(connector_cls: type[Connector], process_cls: type[Process]) -> Process:
    """Build a process with the given connector and process class."""
    comp_a = A(name="comp_a", iters=ITERS)
    comp_b1 = B(name="comp_b1", factor=1)
    comp_b2 = B(name="comp_b2", factor=2)
    components = [comp_a, comp_b1, comp_b2]
    connectors = [
        connector_cls(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b1.in_1")),
        connector_cls(spec=ConnectorSpec(source="comp_b1.out_1", target="comp_b2.in_1")),
    ]
    return process_cls(components=components, connectors=connectors)


@pytest.mark.benchmark
@pytest.mark.parametrize(
    "connector_cls, process_cls",
    CONNECTOR_PROCESS_PARAMS,
    ids=CONNECTOR_PROCESS_IDS,
)
@pytest.mark.asyncio
async def test_benchmark_process_lifecycle(
    connector_cls: type[Connector],
    process_cls: type[Process],
    ray_ctx: None,
) -> None:
    """Benchmark the full lifecycle (init, run, destroy) of a Plugboard Process."""
    process = _build_process(connector_cls, process_cls)
    async with process:
        await process.run()


@pytest.mark.parametrize(
    "connector_cls, process_cls",
    CONNECTOR_PROCESS_PARAMS,
    ids=CONNECTOR_PROCESS_IDS,
)
def test_benchmark_process_run(
    benchmark: BenchmarkFixture,
    connector_cls: type[Connector],
    process_cls: type[Process],
    ray_ctx: None,
) -> None:
    """Benchmark running of a Plugboard Process."""
    process = _build_process(connector_cls, process_cls)

    def _setup() -> None:
        uvloop.run(process.init())

    def _run() -> None:
        uvloop.run(process.run())

    benchmark.pedantic(_run, setup=_setup, rounds=5)
