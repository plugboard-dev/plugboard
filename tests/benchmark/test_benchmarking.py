"""Simple benchmark tests for Plugboard models."""

import asyncio

from pytest_benchmark.fixture import BenchmarkFixture

from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess, Process
from plugboard.schemas import ConnectorSpec
from tests.integration.test_process_with_components_run import A, B


def _setup_process() -> tuple[tuple[Process], dict]:
    comp_a = A(name="comp_a", iters=1000)
    comp_b1 = B(name="comp_b1", factor=1)
    comp_b2 = B(name="comp_b2", factor=2)
    components = [comp_a, comp_b1, comp_b2]
    connectors = [
        AsyncioConnector(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b1.in_1")),
        AsyncioConnector(spec=ConnectorSpec(source="comp_b1.out_1", target="comp_b2.in_1")),
    ]
    process = LocalProcess(components=components, connectors=connectors)
    # Initialise process so that this is excluded from the benchmark timing
    asyncio.run(process.init())
    # Return args and kwargs tuple for benchmark.pedantic
    return (process,), {}


def _run_process(process: Process) -> None:
    asyncio.run(process.run())


def test_benchmark_process_run(benchmark: BenchmarkFixture) -> None:
    """Benchmark the running of a Plugboard Process."""
    benchmark.pedantic(_run_process, setup=_setup_process, rounds=5)
