"""Regression checks for benchmark event-loop ownership and failure cleanup."""

import asyncio
from collections.abc import Callable
from unittest.mock import Mock

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from tests.benchmark.test_benchmarking import Phase, test_benchmark_process as run_benchmark
from tests.benchmark.workloads import Workload


@pytest.mark.parametrize("phase", ["init", "run", "lifecycle"])
def test_benchmark_destroys_failed_process_on_its_own_loop(phase: Phase) -> None:
    """Failed initialization/execution must clean up before the owning loop closes."""
    loops: list[asyncio.AbstractEventLoop] = []

    class FailingProcess:
        async def init(self) -> None:
            loops.append(asyncio.get_running_loop())
            if phase != "run":
                raise RuntimeError("initialization failed")

        async def run(self) -> None:
            loops.append(asyncio.get_running_loop())
            raise RuntimeError("execution failed")

        async def destroy(self) -> None:
            loops.append(asyncio.get_running_loop())

    workload = Mock(spec=Workload)
    workload.topology = "chain"
    workload.size = 3
    workload.build.return_value = (FailingProcess(), [])
    benchmark = Mock(spec=BenchmarkFixture)
    benchmark.extra_info = {}

    def pedantic(
        target: Callable[[], None],
        *,
        setup: Callable[[], None],
        teardown: Callable[[], None],
        rounds: int,
        iterations: int,
    ) -> None:
        # Like pytest-benchmark, failure skips the teardown callback.
        setup()
        target()

    benchmark.pedantic.side_effect = pedantic
    with pytest.raises(RuntimeError, match="failed"):
        run_benchmark(benchmark, workload, phase)

    assert len(loops) == (3 if phase == "run" else 2)
    assert all(loop is loops[0] for loop in loops)
    assert loops[0].is_closed()
