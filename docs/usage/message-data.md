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

All four build on the [`MessageDataReader`][plugboard.library.MessageDataReader] and
[`MessageDataWriter`][plugboard.library.MessageDataWriter] base classes, which handle
connecting, reconnection with backoff, batching and acknowledgment.

## Installing

Each broker uses its own client library, supplied as an extra:

```shell
pip install "plugboard[gcp-pubsub]"     # google-cloud-pubsub
pip install "plugboard[aws-messaging]"  # aiobotocore
```

Constructing a component without its extra raises an `ImportError` naming the extra to
install.

## Reading and writing records

Messages are expected to carry a JSON object per record, whose keys match
`field_names`:

```python
import asyncio

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.library import AWSSNSDataWriter, GCPPubSubDataReader
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec


class Bucket(Component):
    """Turns a raw measurement into a bucketed label before it leaves the model."""

    io = IO(inputs=["x", "y"], outputs=["bucket"])

    async def step(self) -> None:
        self.bucket = "high" if self.x + self.y > 50 else "low"


async def main() -> None:
    reader = GCPPubSubDataReader(
        name="reader",
        subscription_id="measurements-pull",
        # project_id is optional; it defaults to the GCP_PUBSUB_PROJECT_ID variable
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
            AsyncioConnector(spec=ConnectorSpec(source="reader.x", target="bucket.x")),
            AsyncioConnector(spec=ConnectorSpec(source="reader.y", target="bucket.y")),
            AsyncioConnector(spec=ConnectorSpec(source="bucket.bucket", target="writer.bucket")),
        ],
    )
    async with process:
        await process.run()


asyncio.run(main())
```

The components are ordinary `Component`s, so they also work in a `RayProcess` and with
any connector.

## Behaviour worth knowing

- **A reader waits; it does not finish.** An empty poll means "nothing yet", not "no
  more data" (unlike a file). A reader started before its producer keeps running and
  picks up messages as they arrive; to end a run that would otherwise wait forever, stop
  the process. A reader only stops on its own when the broker reports the source as gone
  (for example a deleted subscription or queue), at which point it closes its stream and
  the run ends.
- **Messages are acknowledged after they are processed.** A batch is acknowledged only
  once every record in it has been published downstream, so a crash mid-batch leaves the
  rest to be redelivered (at-least-once). For SQS, "acknowledge" means deleting the
  messages.
- **Writers batch by `chunk_size`.** A writer flushes to the broker when its input
  buffer reaches `chunk_size` records, and flushes whatever is left over when the run
  ends. `chunk_size` defaults to `None`, so a writer with no `chunk_size` buffers every
  record in memory and publishes them all at the end rather than streaming during the
  run — set `chunk_size` (for example `chunk_size=1` for live per-record publishing) to
  stream. For SQS the effective size is capped at 10 messages per send, the broker
  limit.
- **Failures are retried with backoff.** Transient broker errors trigger a reconnect and
  retry; permanent errors (such as `AccessDenied`) fail immediately. Override the policy
  with the `retry_policy` argument, e.g.
  `retry_policy=RetryPolicy(max_retries=5, base_delay=0.5, max_delay=30.0)`; an empty
  poll pauses for `idle_poll_delay` seconds.
- **Encoding.** By default each record is JSON-encoded (`parse_json=True`). With
  `parse_json=False` a writer sends only the first field's value and a reader exposes the
  raw payload under a `data` field.
- **SNS fan-out is transparent.** Subscribing an SQS queue to an SNS topic delivers the
  notification envelope, which `AWSSQSDataReader` unwraps automatically; a non-object
  body is exposed under `data`.

## Configuration

Connection details are passed explicitly or read from the environment (explicit arguments
always win), so the same model can target a different account or region without code
changes. The message-data components read the `GCP_PUBSUB_PROJECT_ID` and `AWS_REGION`
environment variables; see [Configuration](configuration.md#message-data-brokers) for
how these are resolved. Credentials are never configured through Plugboard — the clients
use their normal provider mechanisms (Application Default Credentials for PubSub, and the
standard AWS credential chain for SQS/SNS).
