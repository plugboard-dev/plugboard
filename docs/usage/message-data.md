# Message Data

Message data components read and write **records** through a pub/sub message broker,
rather than through a channel wired between components. They are the broker equivalent
of [`FileReader`][plugboard.library.FileReader] / [`FileWriter`][plugboard.library.FileWriter]:
each message carries one record, and the fields named by `field_names` become the
component's outputs (for a reader) or inputs (for a writer).

| Class | Broker | Reads from | Writes to |
|---|---|---|---|
| [`GCPPubSubDataReader`][plugboard.library.GCPPubSubDataReader] | Google Cloud PubSub | a subscription | |
| [`GCPPubSubDataWriter`][plugboard.library.GCPPubSubDataWriter] | Google Cloud PubSub | | a topic |
| [`AWSSQSDataReader`][plugboard.library.AWSSQSDataReader] | AWS SQS | a queue | |
| [`AWSSNSDataWriter`][plugboard.library.AWSSNSDataWriter] | AWS SNS | | a topic |
| [`KafkaDataReader`][plugboard.library.KafkaDataReader] | Apache Kafka | a topic + consumer group | |
| [`KafkaDataWriter`][plugboard.library.KafkaDataWriter] | Apache Kafka | | a topic |

All six build on the [`MessageDataReader`][plugboard.library.MessageDataReader] and
[`MessageDataWriter`][plugboard.library.MessageDataWriter] base classes, which handle
connecting, reconnection with backoff, batching and acknowledgment.

## Installing

Each broker uses its own client library, supplied as an extra:

```shell
pip install "plugboard[gcp-pubsub]"     # google-cloud-pubsub
pip install "plugboard[aws-messaging]"  # aiobotocore
pip install "plugboard[kafka]"          # aiokafka
```

Constructing a component without its extra raises an `ImportError` naming the extra to
install.

## Reading and writing records

Messages are expected to carry a JSON object per record, whose keys match
`field_names`:

```python
import asyncio

from plugboard.component import Component, IOController as IO
from plugboard.library import AWSSNSDataWriter, GCPPubSubDataReader
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec


class Bucket(Component):
    """Turns a raw measurement into a bucketed label before it leaves the model."""

    io = IO(inputs=["x", "y"], outputs=["bucket"])

    async def step(self) -> None:
        self.bucket = "high" if self.y > 50 else "low"


async def main() -> None:
    reader = GCPPubSubDataReader(
        name="reader",
        subscription_id="measurements-pull",
        project_id="plugboard-dev",  # Optional; defaults to GCP_PUBSUB_PROJECT_ID
        field_names=["x", "y"],
        chunk_size=20,
    )
    bucket = Bucket(name="bucket")
    writer = AWSSNSDataWriter(
        name="writer",
        topic_arn="arn:aws:sns:eu-west-1:123456789012:measurements",
        region="eu-west-1",  # Optional; defaults to AWS_REGION
        field_names=["bucket"],
        chunk_size=20,
    )

    process = LocalProcess(
        name="measurements",
        components=[reader, bucket, writer],
        connectors=[
            ConnectorSpec(source="reader.x", target="bucket.x"),
            ConnectorSpec(source="reader.y", target="bucket.y"),
            ConnectorSpec(source="bucket.bucket", target="writer.bucket"),
        ],
    )
    await process.run()


asyncio.run(main())
```

The components are ordinary `Component`s, so they also work in a `RayProcess` and with
any connector.

## Behaviour worth knowing

**A reader waits; it does not finish.** An empty poll from a broker means "nothing yet",
not "no more data" — unlike a file, which ends. A reader started before its producer
keeps running and picks up messages as they arrive. To end a reader's stream, the broker
must report the source as gone (for example a deleted PubSub subscription or SQS queue),
which raises `IOStreamClosedError` like other data readers do. Stop the process to end a
run that would otherwise wait forever.

**Messages are acknowledged after they are processed.** A batch fetched from the broker
is acknowledged only once every record in it has been published downstream, so a crash
mid-batch leaves the unread messages to be redelivered (at-least-once). For SQS,
"acknowledge" means deleting the messages; for Kafka it means committing the offsets of
the processed records, per partition.

**Batching is bounded by the broker.** `chunk_size` sets how many messages are fetched
per poll (and per send for writers). SQS delivers at most 10 messages per call, so a
larger `chunk_size` is capped there and a warning is logged.

**Failures are retried with backoff.** Transient broker errors trigger a reconnect and a
retry, doubling the delay up to a cap. Permanent errors — such as `AccessDenied` or a
deleted topic — fail immediately instead of burning the retries. Both the classification
and the policy are handled by the base classes:

```python
from plugboard.library import KafkaDataReader
from plugboard.utils.retry import RetryPolicy

reader = KafkaDataReader(
    name="reader",
    topic="measurements",
    group_id="plugboard",
    field_names=["x", "y"],
    bootstrap_servers="localhost:9092",  # Optional; defaults to KAFKA_BOOTSTRAP_SERVERS
    retry_policy=RetryPolicy(max_retries=5, base_delay=0.5, max_delay=30.0),
    idle_poll_delay=0.5,  # Pause between empty polls, if the broker returns immediately
)
```

**Message encoding.** By default each record is JSON-encoded (`parse_json=True`). With
`parse_json=False` a writer sends only the first field's value, and a reader exposes the
raw payload under a `data` field — useful for single-value or binary messages.

## Configuration

Connection details can be passed explicitly or read from the environment, which lets the
same model run against a different account or region without code changes. Explicit
arguments always win.

| Option Name               | Description                              | Used by |
|---------------------------|------------------------------------------|---------|
| `GCP_PUBSUB_PROJECT_ID`   | Default GCP project for PubSub topics    | `GCPPubSubDataReader`, `GCPPubSubDataWriter` |
| `AWS_REGION`              | Default AWS region for SQS/SNS clients   | `AWSSQSDataReader`, `AWSSNSDataWriter` |
| `KAFKA_BOOTSTRAP_SERVERS` | Default Kafka broker address(es)         | `KafkaDataReader`, `KafkaDataWriter` |

Credentials themselves are never configured through Plugboard: the clients use their
normal provider mechanisms (Application Default Credentials for PubSub, the standard AWS
credential chain, SASL settings for Kafka).
