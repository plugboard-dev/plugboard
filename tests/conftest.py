"""Configuration for the test suite."""

from abc import ABC
from asyncio.events import BaseDefaultEventLoopPolicy
import multiprocessing
import os
import typing as _t
from unittest.mock import patch

import pytest
import pytest_asyncio
import pytest_cases
import ray
from that_depends import ContextScopes, container_context
import uvloop

from plugboard.component import Component, IOController as IO
from plugboard.component.io_controller import IOStreamClosedError
from plugboard.connector import ZMQConnector
from plugboard.schemas.state import Status
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings


@pytest.fixture(scope="session")
def event_loop_policy() -> BaseDefaultEventLoopPolicy:
    """Set uvloop as the event loop policy for the test session."""
    return uvloop.EventLoopPolicy()


@pytest.fixture(scope="session", autouse=True)
def mp_set_start_method() -> None:
    """Set the start method for multiprocessing to 'spawn'."""
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method can only be set once per process
        pass


@pytest.fixture(scope="session")
def ray_ctx() -> _t.Iterator[None]:
    """Initialises and shuts down Ray."""
    ray.init(num_cpus=4, num_gpus=0, include_dashboard=True)
    yield
    ray.shutdown()


@pytest.fixture(scope="function")
def job_id_ctx() -> _t.Iterator[str]:
    """Enters the container context with the job_id."""
    with container_context(DI, global_context={"job_id": None}, scope=ContextScopes.APP):
        job_id = DI.job_id.resolve_sync()
        yield job_id


@pytest_asyncio.fixture(scope="function", autouse=True)
async def DI_teardown() -> _t.AsyncGenerator[None, None]:
    """Cleans up any resources created in DI container after each test."""
    try:
        yield
    finally:
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
        DI.settings.override_sync(testing_settings)
        yield ZMQConnector
        DI.settings.reset_override_sync()


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

    async def step(self) -> None:  # noqa: D102
        self._step_count += 1

    async def run(self) -> None:  # noqa: D102
        self._is_running = True
        await self._set_status(Status.RUNNING)
        try:
            while True:
                try:
                    await self.step()
                except IOStreamClosedError:
                    break
                if self._max_steps > 0 and self._step_count >= self._max_steps:
                    break
            if self.status not in {Status.STOPPED, Status.FAILED}:
                await self._set_status(Status.COMPLETED)
        finally:
            self._is_running = False
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
