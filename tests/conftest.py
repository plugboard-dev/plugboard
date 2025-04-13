"""Configuration for the test suite."""

from abc import ABC, abstractmethod
import multiprocessing
import os
import typing as _t
from unittest.mock import patch

import pytest
import pytest_cases
import ray

from plugboard.component import Component, IOController as IO
from plugboard.component.io_controller import IOStreamClosedError
from plugboard.connector import ZMQConnector
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings


@pytest.fixture(scope="session", autouse=True)
def mp_set_start_method() -> None:
    """Set the start method for multiprocessing to 'spawn'."""
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method can only be set once per process
        pass


@pytest.fixture(scope="session")
def ray_context() -> _t.Iterator[None]:
    """Initialises and shuts down Ray."""
    ray.init(num_cpus=2, num_gpus=0, include_dashboard=False)
    yield
    ray.shutdown()


@pytest.fixture(scope="function", autouse=True)
async def DI_teardown() -> _t.AsyncIterable[None]:
    """Cleans up any resources created in DI container after each test."""
    yield
    await DI.tear_down()


@pytest_cases.fixture
@pytest_cases.parametrize(zmq_pubsub_proxy=[False, True])
def zmq_connector_cls(zmq_pubsub_proxy: bool) -> _t.Iterator[_t.Type[ZMQConnector]]:
    """Returns the ZMQConnector class with the specified proxy setting.

    Patches the env var `PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY` to control the proxy setting.
    """
    with patch.dict(
        os.environ,
        {"PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY": str(zmq_pubsub_proxy)},
    ):
        testing_settings = Settings()
        DI.settings.override(testing_settings)
        yield ZMQConnector
        DI.settings.reset_override()


class ComponentTestHelper(Component, ABC):
    """`ComponentTestHelper` is a component class for testing purposes."""

    io = IO(inputs=[], outputs=[])
    exports = ["_is_initialised", "_is_finished", "_step_count"]

    @property
    def is_initialised(self) -> bool:  # noqa: D102
        return self._is_initialised

    @property
    def is_finished(self) -> bool:  # noqa: D102
        return self._is_finished

    @property
    def step_count(self) -> int:  # noqa: D102
        return self._step_count

    def __init__(self, *args: _t.Any, max_steps: int = 0, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._is_initialised = False
        self._is_finished = False
        self._step_count = 0
        self._max_steps = max_steps

    async def init(self) -> None:  # noqa: D102
        self._is_initialised = True
        await super().init()

    @abstractmethod
    async def step(self) -> None:  # noqa: D102
        self._step_count += 1

    async def run(self) -> None:  # noqa: D102
        while True:
            try:
                await self.step()
            except IOStreamClosedError:
                break
            if self._max_steps > 0 and self._step_count >= self._max_steps:
                break
        self._is_finished = True

    def dict(self) -> dict:
        """Returns the component state as a dictionary."""
        data = super().dict()
        data.update(
            {
                "is_initialised": self._is_initialised,
                "is_finished": self._is_finished,
                "step_count": self._step_count,
            }
        )
        return data
