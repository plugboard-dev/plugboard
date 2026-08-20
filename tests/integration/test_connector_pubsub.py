"""Integration tests for pubsub mode connector against broker/messaging infrastructure."""

import typing as _t

import pytest
from pytest_lazy_fixtures import lf

from plugboard.connector import (
    Connector,
    RabbitMQConnector,
    ZMQConnector,
)
from plugboard.connector.redis_channel import RedisConnector
from plugboard.utils.settings import Settings
from tests.conftest import override_settings
from tests.unit.test_connector_pubsub import (  # noqa: F401
    _HASH_SEED,
    TEST_ITEMS,
    _test_pubsub_channel_multiple_publishers,
    _test_pubsub_channel_multiple_topics_and_publishers,
    _test_pubsub_channel_single_publisher,
)


@pytest.fixture(params=[True], ids=["zmq_pubsub_proxy=True"])
def zmq_connector_cls(request: pytest.FixtureRequest) -> _t.Iterator[_t.Type[ZMQConnector]]:
    """Returns the ZMQConnector class with the specified proxy setting.

    Overrides settings to control the proxy setting without mutating process env.
    """
    testing_settings = Settings.model_validate({"flags": {"zmq_pubsub_proxy": request.param}})
    with override_settings(testing_settings):
        yield ZMQConnector


@pytest.fixture(params=[RabbitMQConnector, lf("zmq_connector_cls"), RedisConnector])
def connector_cls(request: pytest.FixtureRequest) -> type[Connector]:
    """Fixture for `Connector` of various types."""
    return request.param


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "num_subscribers, num_messages",
    [
        (1, 100),
        (10, 100),
    ],
)
async def test_pubsub_channel_single_publisher(
    connector_cls: type[Connector], num_subscribers: int, num_messages: int, job_id_ctx: str
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there is a single publisher. Messages are expected to be received by all
    subscribers exactly once and in order.
    """
    await _test_pubsub_channel_single_publisher(connector_cls, num_subscribers, num_messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "num_publishers, num_subscribers, num_messages",
    [
        (10, 1, 100),
        (10, 10, 100),
    ],
)
async def test_pubsub_channel_multiple_publishers(
    connector_cls: type[Connector],
    num_publishers: int,
    num_subscribers: int,
    num_messages: int,
    job_id_ctx: str,
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there are multiple publishers. Messages are expected to be received by all
    subscribers exactly once but they are not expected to be in order.
    """
    await _test_pubsub_channel_multiple_publishers(
        connector_cls, num_publishers, num_subscribers, num_messages
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "num_topics, num_publishers, num_subscribers, num_messages",
    [
        (3, 10, 1, 100),
        (3, 10, 10, 100),
    ],
)
async def test_pubsub_channel_multiple_topics_and_publishers(
    connector_cls: type[Connector],
    num_topics: int,
    num_publishers: int,
    num_subscribers: int,
    num_messages: int,
    job_id_ctx: str,
) -> None:
    """Tests the various pubsub `Channel` classes in pubsub mode.

    In this test there are multiple topics and publishers. Messages are expected to be received by
    all subscribers exactly once but they are not expected to be in order.
    """
    await _test_pubsub_channel_multiple_topics_and_publishers(
        connector_cls, num_topics, num_publishers, num_subscribers, num_messages
    )
