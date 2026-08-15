"""Provides `GCPPubSubDataReader` and `GCPPubSubDataWriter` for Google Cloud PubSub."""

from __future__ import annotations

from collections import deque
import json
import typing as _t

from plugboard.exceptions import NoMoreDataException
from plugboard.library.message_reader import MessageDataReader, MessageDataReaderArgsDict
from plugboard.library.message_writer import MessageDataWriter, MessageDataWriterArgsDict
from plugboard.utils import depends_on_optional


try:
    from google.cloud import pubsub_v1
    from google.cloud.pubsub_v1.subscriber.message import Message as PubSubMessage
except ImportError:  # pragma: no cover
    pass


class GCPPubSubDataReaderArgsDict(MessageDataReaderArgsDict):
    """Specification of the `GCPPubSubDataReader` constructor arguments.

    Attributes:
        project_id: The GCP project ID.
        subscription_id: The PubSub subscription ID.
        parse_json: Whether to parse message data as JSON.
    """

    project_id: str
    subscription_id: str
    parse_json: _t.NotRequired[bool]


class GCPPubSubDataWriterArgsDict(MessageDataWriterArgsDict):
    """Specification of the `GCPPubSubDataWriter` constructor arguments.

    Attributes:
        project_id: The GCP project ID.
        topic_id: The PubSub topic ID.
        parse_json: Whether to encode message data as JSON.
    """

    project_id: str
    topic_id: str
    parse_json: _t.NotRequired[bool]


class GCPPubSubDataReader(MessageDataReader):
    """Reads data from a Google Cloud PubSub subscription.

    Messages are pulled from the subscription in batches and converted
    to field values. Messages are acknowledged after processing.
    """

    @depends_on_optional("google.cloud.pubsub_v1", extra="gcp-pubsub")
    def __init__(
        self,
        project_id: str,
        subscription_id: str,
        parse_json: bool = True,
        **kwargs: _t.Unpack[GCPPubSubDataReaderArgsDict],
    ) -> None:
        """Instantiates the `GCPPubSubDataReader`.

        Args:
            project_id: The GCP project ID.
            subscription_id: The PubSub subscription ID.
            parse_json: Whether to parse message data as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        topic = kwargs.pop("topic", f"{project_id}/{subscription_id}")
        super().__init__(topic=topic, **kwargs)
        self._project_id = project_id
        self._subscription_id = subscription_id
        self._subscription_path = (
            f"projects/{project_id}/subscriptions/{subscription_id}"
        )
        self._parse_json = parse_json
        self._subscriber: _t.Optional[pubsub_v1.SubscriberClient] = None

    async def _connect(self) -> None:
        """Creates a PubSub subscriber client."""
        self._subscriber = pubsub_v1.SubscriberClient()

    async def _disconnect(self) -> None:
        """Closes the PubSub subscriber client."""
        if self._subscriber is not None:
            self._subscriber.close()
            self._subscriber = None

    async def _receive(self) -> list[_t.Any]:
        """Pulls a batch of messages from the PubSub subscription.

        Returns:
            A list of PubSub `Message` objects.

        Raises:
            NoMoreDataException: If the subscription is deleted or unreachable.
        """
        if self._subscriber is None:
            raise RuntimeError("Subscriber client not initialized")
        max_messages = self._chunk_size or 10
        try:
            response = self._subscriber.pull(
                request={"subscription": self._subscription_path, "max_messages": max_messages},
                timeout=30.0,
            )
        except Exception as e:
            if "NOT_FOUND" in str(e) or "Subscription not found" in str(e):
                raise NoMoreDataException from e
            raise
        if not response.received_messages:
            return []
        return list(response.received_messages)

    async def _convert(self, messages: list[_t.Any]) -> dict[str, deque]:
        """Converts PubSub messages to a field buffer.

        Args:
            messages: A list of `ReceivedMessage` objects.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for msg_wrapper in messages:
            data = msg_wrapper.message.data
            if self._parse_json:
                record = json.loads(data.decode("utf-8"))
            else:
                record = {"data": data}
            for field in self.io.outputs:
                converted[field].append(record.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        """Acknowledges processed PubSub messages.

        Args:
            messages: The `ReceivedMessage` objects to acknowledge.
        """
        if self._subscriber is None:
            raise RuntimeError("Subscriber client not initialized")
        ack_ids = [msg_wrapper.ack_id for msg_wrapper in messages]
        self._subscriber.acknowledge(
            request={"subscription": self._subscription_path, "ack_ids": ack_ids}
        )


class GCPPubSubDataWriter(MessageDataWriter):
    """Writes data to a Google Cloud PubSub topic.

    Field data is converted to JSON-encoded messages and published
    to the specified topic.
    """

    @depends_on_optional("google.cloud.pubsub_v1", extra="gcp-pubsub")
    def __init__(
        self,
        project_id: str,
        topic_id: str,
        parse_json: bool = True,
        **kwargs: _t.Unpack[GCPPubSubDataWriterArgsDict],
    ) -> None:
        """Instantiates the `GCPPubSubDataWriter`.

        Args:
            project_id: The GCP project ID.
            topic_id: The PubSub topic ID.
            parse_json: Whether to encode message data as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        topic = kwargs.pop("topic", f"{project_id}/{topic_id}")
        super().__init__(topic=topic, **kwargs)
        self._project_id = project_id
        self._topic_id = topic_id
        self._topic_path = f"projects/{project_id}/topics/{topic_id}"
        self._parse_json = parse_json
        self._publisher: _t.Optional[pubsub_v1.PublisherClient] = None

    async def _connect(self) -> None:
        """Creates a PubSub publisher client."""
        self._publisher = pubsub_v1.PublisherClient()

    async def _disconnect(self) -> None:
        """Closes the PubSub publisher client."""
        if self._publisher is not None:
            self._publisher.close()  # type: ignore[no-untyped-call]
            self._publisher = None

    async def _send(self, messages: list[_t.Any]) -> None:
        """Publishes messages to the PubSub topic.

        Args:
            messages: A list of bytes objects to publish.
        """
        if self._publisher is None:
            raise RuntimeError("Publisher client not initialized")
        futures = []
        for msg_data in messages:
            future = self._publisher.publish(self._topic_path, data=msg_data)
            futures.append(future)
        # Wait for all publishes to complete
        for future in futures:
            future.result(timeout=60.0)

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded bytes messages.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of bytes objects ready to publish.
        """
        completed_rows = min(len(d) for d in data.values()) if data else 0
        messages: list[bytes] = []
        for i in range(completed_rows):
            record = {field: data[field][i] for field in data}
            if self._parse_json:
                messages.append(json.dumps(record).encode("utf-8"))
            else:
                # Send raw data from the first field
                first_field = next(iter(record.values()))
                messages.append(
                    first_field if isinstance(first_field, bytes) else str(first_field).encode()
                )
        return messages
