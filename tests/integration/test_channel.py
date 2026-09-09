"""Integration tests for channels against broker/messaging infrastructure."""

import os
import typing as _t
from unittest.mock import patch

from plugboard_schemas.connector import ConnectorMode, ConnectorSpec
import pytest

from plugboard.connector import (
    Connector,
    RabbitMQConnector,
    ZMQConnector,
)
from plugboard.connector.redis_channel import RedisConnector
from plugboard.utils import DI
from plugboard.utils.settings import Settings
from tests.conftest import ConnectorCase, configured_connector, connector_case_id
from tests.unit.test_channel import (  # noqa: F401
    TEST_ITEMS,
    test_channel,
    test_multiprocessing_channel,
)


@pytest.fixture(
    params=[
        ConnectorCase(RabbitMQConnector),
        ConnectorCase(ZMQConnector, True),
        ConnectorCase(RedisConnector),
    ],
    ids=connector_case_id,
)
def connector_cls(request: pytest.FixtureRequest) -> _t.Iterator[type[Connector]]:
    """Configure each connector variant for this test module."""
    with configured_connector(request.param) as cls:
        yield cls


@pytest.fixture(
    params=[
        ConnectorCase(RabbitMQConnector),
        ConnectorCase(ZMQConnector, True),
        ConnectorCase(RedisConnector),
    ],
    ids=connector_case_id,
)
def connector_cls_mp(request: pytest.FixtureRequest) -> _t.Iterator[type[Connector]]:
    """Configure each connector variant for this test module."""
    with configured_connector(request.param) as cls:
        yield cls


@pytest.mark.parametrize("connector_cls", [RabbitMQConnector, RedisConnector])
async def test_channel_broker_url_unset(connector_cls: type[Connector], job_id_ctx: str) -> None:
    """Test that attempting to connect a channel without the broker URL set raises an error."""
    spec = ConnectorSpec(mode=ConnectorMode.PIPELINE, source="test.send", target="test.recv")
    with patch.dict(
        os.environ,
        {
            "RABBITMQ_URL": "",
            "REDIS_URL": "",
        },
    ):
        with DI.override_providers_sync({"settings": Settings()}):
            if connector_cls is RabbitMQConnector:
                with pytest.raises(RuntimeError, match="RabbitMQ connection not available"):
                    await connector_cls(spec=spec).connect_send()
            elif connector_cls is RedisConnector:
                with pytest.raises(RuntimeError, match="Redis client not available"):
                    await connector_cls(spec=spec).connect_send()
