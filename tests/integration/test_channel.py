"""Integration tests for channels against broker/messaging infrastructure."""

import os
import typing as _t
from unittest.mock import patch

import pytest_cases

from plugboard.connector import (
    Connector,
    RabbitMQConnector,
    ZMQConnector,
)
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings
from tests.unit.test_channel import (  # noqa: F401
    TEST_ITEMS,
    test_channel,
    test_multiprocessing_channel,
)


@pytest_cases.fixture
@pytest_cases.parametrize(zmq_pubsub_proxy=[True])
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


@pytest_cases.fixture
@pytest_cases.parametrize("_connector_cls", [RabbitMQConnector, zmq_connector_cls])
def connector_cls(_connector_cls: type[Connector]) -> type[Connector]:
    """Fixture for `Connector` of various types."""
    return _connector_cls


@pytest_cases.fixture
@pytest_cases.parametrize("_connector_cls_mp", [RabbitMQConnector, zmq_connector_cls])
def connector_cls_mp(_connector_cls_mp: type[Connector]) -> type[Connector]:
    """Fixture for `Connector` of various types for use in multiprocess context."""
    return _connector_cls_mp
