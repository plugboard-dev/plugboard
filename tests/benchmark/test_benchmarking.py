"""Benchmark tests for Plugboard processes."""

import asyncio

import pytest

from plugboard.connector import AsyncioConnector, Connector, ZMQConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from tests.integration.test_process_with_components_run import A, B


ITERS = 1000


def _build_process(connector_cls: type[Connector]) -> LocalProcess:
    """Build a process with the given connector class."""
    comp_a = A(name="comp_a", iters=ITERS)
    comp_b1 = B(name="comp_b1", factor=1)
    comp_b2 = B(name="comp_b2", factor=2)
    components = [comp_a, comp_b1, comp_b2]
    connectors = [
        connector_cls(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b1.in_1")),
        connector_cls(spec=ConnectorSpec(source="comp_b1.out_1", target="comp_b2.in_1")),
    ]
    return LocalProcess(components=components, connectors=connectors)


@pytest.mark.benchmark
@pytest.mark.parametrize(
    "connector_cls",
    [AsyncioConnector, ZMQConnector],
    ids=["asyncio", "zmq"],
)
def test_benchmark_process_run(connector_cls: type[Connector]) -> None:
    """Benchmark the init and run of a Plugboard Process."""

    async def _run() -> None:
        process = _build_process(connector_cls)
        await process.init()
        await process.run()

    asyncio.run(_run())


@pytest.mark.benchmark
@pytest.mark.parametrize(
    "connector_cls",
    [AsyncioConnector, ZMQConnector],
    ids=["asyncio", "zmq"],
)
def test_benchmark_process_lifecycle(connector_cls: type[Connector]) -> None:
    """Benchmark the full lifecycle (init, run, destroy) of a Plugboard Process."""

    async def _lifecycle() -> None:
        process = _build_process(connector_cls)
        await process.init()
        await process.run()
        await process.destroy()

    asyncio.run(_lifecycle())
