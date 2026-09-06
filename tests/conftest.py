"""Configuration for the test suite."""

from abc import ABC
import asyncio
from contextlib import contextmanager
import multiprocessing
import typing as _t
from unittest.mock import patch

import msgspec
import pytest
import pytest_asyncio
from that_depends import ContextScopes, container_context
import uvloop

from plugboard.component import Component, IOController as IO
from plugboard.component.io_controller import IOStreamClosedError
from plugboard.connector import Connector
from plugboard.schemas import Status
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings


@contextmanager
def override_settings(settings: Settings) -> _t.Iterator[None]:
    """Temporarily override DI settings for a test and always reset the override."""
    DI.settings.override_sync(settings)
    try:
        yield
    finally:
        DI.settings.reset_override_sync()


@pytest.hookimpl
def pytest_asyncio_loop_factories() -> dict[str, _t.Callable[[], asyncio.AbstractEventLoop]]:
    """Configure pytest-asyncio to create event loops with uvloop."""
    return {"uvloop": uvloop.new_event_loop}


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
    """Initialises and shuts down Ray.

    Includes a small amount of resources to allow testing of resource-constrained components.
    """
    import ray

    ray.init(num_cpus=5, num_gpus=1, resources={"custom_hardware": 10}, include_dashboard=False)
    try:
        yield
    finally:
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


class ConnectorCase(msgspec.Struct, frozen=True):
    """Connector implementation and optional ZMQ proxy setting for a test case."""

    connector_cls: type[Connector]
    zmq_pubsub_proxy: bool | None = None


def connector_case_id(value: object) -> str | None:
    """Name connector cases while leaving other parameter IDs to pytest."""
    if not isinstance(value, ConnectorCase):
        return None
    name = value.connector_cls.__name__
    if value.zmq_pubsub_proxy is not None:
        name += f"-zmq_pubsub_proxy={value.zmq_pubsub_proxy}"
    return name


@contextmanager
def configured_connector(case: ConnectorCase) -> _t.Iterator[type[Connector]]:
    """Apply a connector case's settings until fixture teardown, including on failure."""
    if case.zmq_pubsub_proxy is None:
        yield case.connector_cls
    else:
        settings = Settings.model_validate({"flags": {"zmq_pubsub_proxy": case.zmq_pubsub_proxy}})
        with override_settings(settings):
            yield case.connector_cls


@pytest.fixture
def connector_cls(request: pytest.FixtureRequest) -> _t.Iterator[type[Connector]]:
    """Resolve connector cases supplied through indirect parametrization."""
    with configured_connector(request.param) as cls:
        yield cls


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


@pytest.fixture
def patch_validate_process() -> _t.Iterator[None]:
    """Patch process validation for tests that don't require functional processes."""
    with (
        patch("plugboard.schemas.validate_process", return_value=[]),
        patch("plugboard.process.process.validate_process", return_value=[]),
    ):
        yield
