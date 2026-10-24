"""Measure lifecycle and execution costs across representative local process graphs."""

import asyncio
import typing as _t

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from plugboard.process import LocalProcess
from tests.benchmark.workloads import Relay, Workload, verify


WORKLOADS = [
    Workload("chain", 3),
    Workload("chain", 16),
    Workload("fan_out", 2),
    Workload("fan_out", 16),
    Workload("fan_in", 2),
    Workload("fan_in", 16),
    Workload("diamond", 4),
    Workload("feedback", 3),
]
MESSAGES = 1000
Phase = _t.Literal["init", "run", "lifecycle"]


@pytest.mark.parametrize("workload", WORKLOADS, ids=lambda workload: workload.id)
@pytest.mark.parametrize("phase", ["init", "run", "lifecycle"])
def test_benchmark_process(benchmark: BenchmarkFixture, workload: Workload, phase: Phase) -> None:
    """Time one lifecycle phase per fresh graph, using one loop for its entire lifetime."""
    process: LocalProcess | None = None
    expected: list[tuple[Relay, int]] = []
    needs_destroy = False
    benchmark.group = phase
    benchmark.extra_info.update(
        topology=workload.topology, size=workload.size, messages_per_source=MESSAGES
    )

    with asyncio.Runner() as runner:

        async def setup_round() -> None:
            nonlocal process, expected, needs_destroy
            process, expected = workload.build(MESSAGES)
            needs_destroy = True
            if phase == "run":
                await process.init()

        async def measure() -> None:
            nonlocal needs_destroy
            assert process is not None
            if phase == "lifecycle":
                try:
                    await process.init()
                    await process.run()
                finally:
                    await process.destroy()
                    needs_destroy = False
            elif phase == "init":
                await process.init()
            else:
                await process.run()

        async def finish_round() -> None:
            nonlocal needs_destroy
            if process is None:
                return
            try:
                if phase == "init":
                    assert process.is_initialised
                else:
                    verify(process, expected, MESSAGES)
            finally:
                if needs_destroy:
                    await process.destroy()
                    needs_destroy = False

        try:
            benchmark.pedantic(
                lambda: runner.run(measure()),
                setup=lambda: runner.run(setup_round()),
                teardown=lambda: runner.run(finish_round()),
                rounds=5,
                iterations=1,
            )
            # Disabled benchmarks execute once without invoking their teardown callback.
            if benchmark.disabled:
                runner.run(finish_round())
        finally:
            # Failed setup/targets also bypass pytest-benchmark's teardown callback.
            if process is not None and needs_destroy:
                runner.run(process.destroy())
