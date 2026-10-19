"""Integration tests for the message broker `MessageDataReader`/`MessageDataWriter` implementations.

These tests exercise the AWS SQS/SNS and GCP PubSub readers and writers against
real broker infrastructure. They are gated behind the ``PLUGBOARD_MESSAGE_BROKER_TESTS``
environment variable (default: not run) so the normal CI suite never touches the brokers.
The flag is enabled in the ``test-integration`` job of ``.github/workflows/lint-test.yaml``,
which also injects the ``AWS_*``/``GCP_*`` credentials and resource identifiers provisioned
by ``plugboard-infra``.

AWS uses the credential chain (``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY``), and the GCP
PubSub client uses Application Default Credentials (``GOOGLE_APPLICATION_CREDENTIALS``).

The write side is driven through each writer's own ``_convert``/``_send`` pair - the exact
broker write path - so these tests validate the broker wiring and field<->message encoding
round trip, while the generic buffering/batching logic is already covered by the unit tests.

Hygiene: before each test the queue/subscription is checked, and if it is not empty a
warning is emitted and it is drained; after each test it is drained again so no messages
from a failed run interfere with the next one.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import typing as _t
import warnings

from aiobotocore.session import get_session as get_boto_session
from google.api_core import exceptions as gcp_exceptions
from google.cloud import pubsub_v1
import pytest

from plugboard.connector import AsyncioConnector
from plugboard.library import (
    AWSSNSDataWriter,
    AWSSQSDataReader,
    GCPPubSubDataReader,
    GCPPubSubDataWriter,
)
from plugboard.schemas import ConnectorSpec


# Gate the whole module behind an opt-in env var (default: skip). The message broker
# integration tests only run when CI has provisioned the real broker infra.
requires_broker = pytest.mark.skipif(
    os.environ.get("PLUGBOARD_MESSAGE_BROKER_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="set PLUGBOARD_MESSAGE_BROKER_TESTS=1 to run message broker integration tests",
)

FIELD_NAMES = ["x", "y"]
# Enough to verify batch delivery, but small so a broken broker fails fast.
RECORDS = [{"x": i, "y": f"value-{i}"} for i in range(1, 6)]
EXPECTED = sorted((record["x"], record["y"]) for record in RECORDS)
_LOG = logging.getLogger(__name__)

# The infra sets the SQS visibility timeout to 30s, so a message a concurrent test received
# but has not deleted is redelivered within ~30s and picked up by a later drain pass. The
# drain declares the queue empty only after several consecutive long-poll timeouts, which
# also absorbs staggered SNS->SQS fan-out delivery.
_DRAIN_TIMEOUT = 90.0
_DRAIN_EMPTY_POLLS = 3  # consecutive empty polls before declaring the queue drained
_DRAIN_POLL_WAIT = 2  # seconds per SQS long poll (also a natural settle between polls)
_DEPTH_CHECK_RETRIES = 3
_DEPTH_CHECK_INTERVAL = 2.0
_READ_TIMEOUT = 60.0


def _broker_env_keys() -> list[str]:
    """The env vars each broker needs, so a missing one is a clear skip, not a crash."""
    aws = ("AWS_SQS_QUEUE_URL", "AWS_SNS_TOPIC_ARN", "AWS_REGION")
    gcp = ("GCP_TOPIC_ID", "GCP_SUBSCRIPTION_ID", "GCP_PUBSUB_PROJECT_ID")
    return list(aws) + list(gcp)


@pytest.fixture
def broker_env() -> _t.Iterator[None]:
    """Skips if any broker identifier is missing, so a partial setup is a clear skip."""
    missing = [key for key in _broker_env_keys() if not os.environ.get(key)]
    if missing:
        pytest.skip(f"missing broker env vars: {', '.join(missing)}")
    yield


async def _aws_queue_depth(queue_url: str, region: str) -> int:
    """Reads the number of messages in the queue (visible + in-flight)."""
    async with get_boto_session().create_client("sqs", region_name=region) as client:
        resp = await client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
        )
        attrs = resp["Attributes"]
        return int(attrs["ApproximateNumberOfMessages"]) + int(
            attrs["ApproximateNumberOfMessagesNotVisible"]
        )


async def _drain_aws_queue(queue_url: str, region: str, *, timeout: float = _DRAIN_TIMEOUT) -> int:
    """Drains an SQS queue (purge, then receive-and-delete) and returns the count deleted.

    Declares the queue empty only after several consecutive long-poll timeouts, so staggered
    SNS->SQS delivery (or messages still becoming visible) does not cause a premature stop.
    """
    deleted = 0
    empty_polls = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with get_boto_session().create_client("sqs", region_name=region) as client:
        with contextlib.suppress(Exception):
            await client.purge_queue(QueueUrl=queue_url)
        while loop.time() < deadline:
            resp = await client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=_DRAIN_POLL_WAIT,
            )
            messages = resp.get("Messages") or []
            if messages:
                await client.delete_message_batch(
                    QueueUrl=queue_url,
                    Entries=[
                        {"Id": str(i), "ReceiptHandle": msg["ReceiptHandle"]}
                        for i, msg in enumerate(messages)
                    ],
                )
                deleted += len(messages)
                empty_polls = 0
            elif empty_polls + 1 >= _DRAIN_EMPTY_POLLS:
                return deleted
            else:
                empty_polls += 1
    return deleted


async def _assert_aws_queue_empty(queue_url: str, region: str) -> None:
    """Retries the depth check to absorb SQS approximate-count eventual consistency."""
    depth = await _aws_queue_depth(queue_url, region)
    for _ in range(_DEPTH_CHECK_RETRIES):
        if depth == 0:
            return
        await asyncio.sleep(_DEPTH_CHECK_INTERVAL)
        depth = await _aws_queue_depth(queue_url, region)
    pytest.fail(f"SQS queue {queue_url} not empty after drain (depth={depth})")


def _gcp_sub_path(project_id: str, subscription_id: str) -> str:
    """The fully-qualified PubSub subscription path."""
    return f"projects/{project_id}/subscriptions/{subscription_id}"


def _gcp_pull_one(project_id: str, subscription_id: str, *, timeout: float) -> list[object]:
    """Pulls up to one batch of messages, returning an empty list if the window elapses.

    Uses only ``pubsub.subscriptions.pull`` (the subscriber role). An empty subscription
    raises ``DeadlineExceeded`` once the pull window elapses; that is reported as "none
    available" rather than a broker error, while any other error propagates so an
    auth/permission problem is not mistaken for an empty broker during setup.
    """
    subscriber = pubsub_v1.SubscriberClient()
    try:
        response = subscriber.pull(
            request={
                "subscription": _gcp_sub_path(project_id, subscription_id),
                "max_messages": 10,
            },
            timeout=timeout,
        )
        return list(response.received_messages)
    except gcp_exceptions.DeadlineExceeded:
        return []
    finally:
        subscriber.close()


def _gcp_subscription_undelivered(project_id: str, subscription_id: str) -> bool:
    """Returns True if the subscription has any available (undelivered) messages."""
    return len(_gcp_pull_one(project_id, subscription_id, timeout=2.0)) > 0


def _drain_gcp_subscription(project_id: str, subscription_id: str, *, timeout: float = 2.0) -> int:
    """Pulls and acknowledges all available messages on the subscription; returns the count."""
    subscriber = pubsub_v1.SubscriberClient()
    acked = 0
    try:
        while True:
            response = subscriber.pull(
                request={
                    "subscription": _gcp_sub_path(project_id, subscription_id),
                    "max_messages": 10,
                },
                timeout=timeout,
            )
            ack_ids = [msg.ack_id for msg in response.received_messages]
            if not ack_ids:
                return acked
            subscriber.acknowledge(
                request={
                    "subscription": _gcp_sub_path(project_id, subscription_id),
                    "ack_ids": ack_ids,
                }
            )
            acked += len(ack_ids)
    except gcp_exceptions.DeadlineExceeded:
        return acked
    finally:
        subscriber.close()


def _log_leftover(message: str, *, pre_test: bool) -> None:
    """Reports a leftover message, escalating to a warning (and a pytest warning) pre-test."""
    if pre_test:
        warnings.warn(message, stacklevel=3)
        _LOG.warning(message)
    else:
        _LOG.info(message)


async def _clean_broker(
    *,
    pre_test: bool,
    queue_url: _t.Optional[str] = None,
    region: _t.Optional[str] = None,
    project_id: _t.Optional[str] = None,
    subscription_id: _t.Optional[str] = None,
) -> None:
    """Ensures a broker is empty.

    In ``pre_test`` mode a non-empty broker emits a warning and is drained, then the empty
    state is asserted (a leftover that cannot be drained fails the test). In post-test mode
    it is drained unconditionally so a failed run leaves nothing for the next one.
    """
    if queue_url and region:
        depth = await _aws_queue_depth(queue_url, region)
        if depth:
            _log_leftover(
                f"SQS queue {queue_url} was not empty ({depth} message(s)); draining",
                pre_test=pre_test,
            )
            await _drain_aws_queue(queue_url, region)
            if pre_test:
                await _assert_aws_queue_empty(queue_url, region)

    if project_id and subscription_id:
        drained = _drain_gcp_subscription(project_id, subscription_id)
        if drained:
            _log_leftover(
                f"PubSub subscription {subscription_id} had {drained} leftover message(s); drained",
                pre_test=pre_test,
            )


@requires_broker
async def test_aws_sns_sqs_round_trip(broker_env: None) -> None:
    """Writes records to the SNS topic and reads them back from the linked SQS queue."""
    queue_url = os.environ["AWS_SQS_QUEUE_URL"]
    topic_arn = os.environ["AWS_SNS_TOPIC_ARN"]
    region = os.environ["AWS_REGION"]

    await _clean_broker(pre_test=True, queue_url=queue_url, region=region)

    writer = AWSSNSDataWriter(
        name="aws-sns-writer",
        field_names=FIELD_NAMES,
        topic_arn=topic_arn,
        region=region,
        parse_json=True,
    )
    reader = AWSSQSDataReader(
        name="aws-sqs-reader",
        field_names=FIELD_NAMES,
        queue_url=queue_url,
        region=region,
        parse_json=True,
        wait_time_seconds=2,
        chunk_size=10,
    )

    writer_channels = await connect_writer(writer)
    await reader.init()
    await writer.init()
    received: list[dict[str, _t.Any]] = []
    try:
        await write_records(writer, writer_channels, RECORDS)
        received = await read_records(reader, len(RECORDS))
        assert sorted((record["x"], record["y"]) for record in received) == EXPECTED
        # The reader acknowledged every record, so nothing should remain on the queue.
        await _assert_aws_queue_empty(queue_url, region)
    finally:
        await writer.destroy()
        await reader.destroy()
        # Safety net: if the read or assertion failed mid-way, drain any unacked
        # leftovers so they do not interfere with the next run.
        await _clean_broker(pre_test=False, queue_url=queue_url, region=region)


@requires_broker
async def test_gcp_pubsub_round_trip(broker_env: None) -> None:
    """Writes records to the PubSub topic and reads them back from the linked subscription."""
    project_id = os.environ["GCP_PUBSUB_PROJECT_ID"]
    topic_id = os.environ["GCP_TOPIC_ID"]
    subscription_id = os.environ["GCP_SUBSCRIPTION_ID"]

    await _clean_broker(pre_test=True, project_id=project_id, subscription_id=subscription_id)

    writer = GCPPubSubDataWriter(
        name="gcp-pubsub-writer",
        field_names=FIELD_NAMES,
        topic_id=topic_id,
        project_id=project_id,
        parse_json=True,
    )
    reader = GCPPubSubDataReader(
        name="gcp-pubsub-reader",
        field_names=FIELD_NAMES,
        subscription_id=subscription_id,
        project_id=project_id,
        parse_json=True,
        chunk_size=10,
        pull_timeout=3,
    )

    writer_channels = await connect_writer(writer)
    await reader.init()
    await writer.init()
    received: list[dict[str, _t.Any]] = []
    try:
        await write_records(writer, writer_channels, RECORDS)
        received = await read_records(reader, len(RECORDS))
        assert sorted((record["x"], record["y"]) for record in received) == EXPECTED
        # The reader acknowledged every record, so the subscription should already be
        # empty. Checked before the finally cleanup drains it, so leftover messages are
        # caught rather than silently removed.
        assert _gcp_subscription_undelivered(project_id, subscription_id) == 0, (
            "PubSub subscription not empty after the round trip"
        )
    finally:
        await writer.destroy()
        await reader.destroy()
        # Clean up so nothing interferes with the next run.
        await _clean_broker(pre_test=False, project_id=project_id, subscription_id=subscription_id)


async def connect_writer(
    writer: AWSSNSDataWriter | GCPPubSubDataWriter,
) -> dict[str, AsyncioConnector]:
    """Connects an input channel to each of the writer's fields.

    Inputs must be connected before the writer is initialised, mirroring the unit tests.
    """
    channels = {
        field: AsyncioConnector(
            spec=ConnectorSpec(source="none.none", target=f"{writer.name}.{field}")
        )
        for field in writer.io.inputs
    }
    await writer.io.connect(list(channels.values()))
    return channels


async def write_records(
    writer: AWSSNSDataWriter | GCPPubSubDataWriter,
    channels: dict[str, AsyncioConnector],
    records: list[dict[str, _t.Any]],
) -> None:
    """Publishes records through the writer's public `Component` lifecycle.

    Each record is sent to the connected input channels and the writer stepped; closing
    and running the writer then flushes the remaining buffer to the broker, so the real
    ``step``/``run``/``_save`` path (not the private broker methods) is exercised.
    """
    senders = {field: await channel.connect_send() for field, channel in channels.items()}
    for record in records:
        for field, value in record.items():
            await senders[field].send(value)
        await writer.step()
    await writer.io.close()
    await writer.run()


async def read_records(
    reader: AWSSQSDataReader | GCPPubSubDataReader,
    expected: int,
    timeout: float = _READ_TIMEOUT,
) -> list[dict[str, _t.Any]]:
    """Steps the reader until ``expected`` records are collected or ``timeout`` elapses.

    A reader waits for the next message rather than closing on an empty poll, so an absent
    message surfaces as a timeout here instead of a silent pass.
    """
    collected: list[dict[str, _t.Any]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(collected) < expected:
        if loop.time() > deadline:
            pytest.fail(f"read {len(collected)}/{expected} records before timeout")
        await reader.step()
        collected.append({field: getattr(reader, field) for field in FIELD_NAMES})
    return collected
