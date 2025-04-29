"""Integration tests for channels against broker/messaging infrastructure."""

import pytest_cases

from plugboard.connector import (
    Connector,
    RabbitMQConnector,
)
from tests.conftest import zmq_connector_cls
from ..unit.test_channel import TEST_ITEMS, test_channel, test_multiprocessing_channel  # noqa: F401


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
