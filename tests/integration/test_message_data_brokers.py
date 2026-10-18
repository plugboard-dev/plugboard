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
"""

from __future__ import annotations

import asyncio
from collections import deque
import os
import typing as _t

import pytest

from plugboard.library import (
    AWSSNSDataWriter,
    AWSSQSDataReader,
    GCPPubSubDataReader,
    GCPPubSubDataWriter,
)


# Gate the whole module behind an opt-in env var (default: skip). The message broker
# integration tests only run when CI has provisioned the real broker infra.
requires_broker = pytest.mark.skipif(
    os.environ.get("PLUGBOARD_MESSAGE_BROKER_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="set PLUGBOARD_MESSAGE_BROKER_TESTS=1 to run message broker integration tests",
)

FIELD_NAMES = ["x", "y"]
# Enough to verify batch delivery, but small so a broken broker fails fast.
RECORDS = [{"x": i, "y": f"value-{i}"} for i in range(1, 6)]


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


@requires_broker
async def test_aws_sns_sqs_round_trip(broker_env: None) -> None:
    """Writes records to the SNS topic and reads them back from the linked SQS queue."""
    queue_url = os.environ["AWS_SQS_QUEUE_URL"]
    topic_arn = os.environ["AWS_SNS_TOPIC_ARN"]
    region = os.environ["AWS_REGION"]

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

    await reader.init()
    await writer.init()
    try:
        await write_records(writer, RECORDS)
    finally:
        await writer.destroy()
        await reader.destroy()

    received = await read_records(reader, len(RECORDS))
    assert sorted(map(tuple, received)) == sorted(map(tuple, RECORDS))


@requires_broker
async def test_gcp_pubsub_round_trip(broker_env: None) -> None:
    """Writes records to the PubSub topic and reads them back from the linked subscription."""
    project_id = os.environ["GCP_PUBSUB_PROJECT_ID"]
    topic_id = os.environ["GCP_TOPIC_ID"]
    subscription_id = os.environ["GCP_SUBSCRIPTION_ID"]

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

    await reader.init()
    await writer.init()
    try:
        await write_records(writer, RECORDS)
    finally:
        await writer.destroy()
        await reader.destroy()

    received = await read_records(reader, len(RECORDS))
    assert sorted(map(tuple, received)) == sorted(map(tuple, RECORDS))


async def write_records(
    writer: AWSSNSDataWriter | GCPPubSubDataWriter,
    records: list[dict[str, _t.Any]],
) -> None:
    """Publishes records through the writer's own convert + send path.

    Building the field buffer as one ``deque`` per field and calling ``_convert`` then
    ``_send`` is exactly how the writer reaches the broker, so this validates the real
    message encoding without depending on the Component input-IO machinery.
    """
    buffer = {field: deque(record[field] for record in records) for field in writer.io.inputs}
    messages = await writer._convert(buffer)
    await writer._send(messages)


async def read_records(
    reader: AWSSQSDataReader | GCPPubSubDataReader,
    expected: int,
    timeout: float = 60.0,
) -> list[dict[str, _t.Any]]:
    """Steps the reader until ``expected`` records are collected or ``timeout`` elapses.

    The reader waits for the next message rather than closing on an empty poll, so an
    absent message surfaces as a timeout here instead of a silent pass.
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
