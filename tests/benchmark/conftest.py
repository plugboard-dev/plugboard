"""Configuration for benchmark tests."""

import typing as _t

import pytest
import ray


@pytest.fixture(scope="session")
def ray_ctx() -> _t.Iterator[None]:
    """Initialises and shuts down Ray for benchmarks.

    Dashboard is disabled to avoid MetricsHead timeout in CI.
    """
    ray.init(num_cpus=5, num_gpus=1, resources={"custom_hardware": 10}, include_dashboard=False)
    yield
    ray.shutdown()
