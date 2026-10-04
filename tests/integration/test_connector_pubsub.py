"""Integration tests for pubsub mode connector against broker/messaging infrastructure."""

import typing as _t

import pytest

from plugboard.connector import (
    Connector,
    RabbitMQConnector,
    ZMQConnector,
)
from plugboard.connector.redis_channel import RedisConnector
from tests.conftest import ConnectorCase, configured_connector, connector_case_id
from tests.unit.test_connector_pubsub import (  # noqa: F401
    _HASH_SEED,
    TEST_ITEMS,
    _test_pubsub_channel_multiple_publishers,
    _test_pubsub_channel_multiple_topics_and_publishers,
    _test_pubsub_channel_single_publisher,
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
