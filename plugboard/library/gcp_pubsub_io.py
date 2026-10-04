"""Provides `GCPPubSubDataReader` and `GCPPubSubDataWriter` for Google Cloud PubSub."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import typing as _t

from plugboard.exceptions import (
    MessageBrokerConnectionError,
    MessageBrokerPermanentError,
    MessageBrokerTransientError,
    NoMoreDataException,
)
from plugboard.library.message_reader import MessageDataReader, MessageDataReaderArgsDict
from plugboard.library.message_writer import (
    MessageDataWriter,
    MessageDataWriterArgsDict,
    encode_records_bytes,
)
from plugboard.utils import DI, depends_on_optional
from plugboard.utils.settings import resolve_argument


try:
    from google.api_core import exceptions as gcp_exceptions
    from google.cloud import pubsub_v1

    # PubSub rejections that retrying cannot resolve, so the retry loop should stop
    # rather than back off repeatedly against a guaranteed failure.
    _PERMANENT_ERRORS: tuple[type[Exception], ...] = (
        gcp_exceptions.PermissionDenied,
        gcp_exceptions.Unauthorized,
        gcp_exceptions.InvalidArgument,
        gcp_exceptions.MethodNotImplemented,
        gcp_exceptions.FailedPrecondition,
    )

    # PubSub failures that are expected to clear on their own, so they are worth retrying.
    _TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
        gcp_exceptions.ServiceUnavailable,
        gcp_exceptions.DeadlineExceeded,
        gcp_exceptions.Aborted,
        gcp_exceptions.InternalServerError,
        gcp_exceptions.BadGateway,
        gcp_exceptions.TooManyRequests,
    )

    _NOT_FOUND_ERRORS: tuple[type[Exception], ...] = (gcp_exceptions.NotFound,)
except ImportError:  # pragma: no cover
    # With the extra not installed, `depends_on_optional` blocks construction and
    # classification is moot: `isinstance(error, ())` never matches.
    _PERMANENT_ERRORS = ()
    _TRANSIENT_ERRORS = ()
    _NOT_FOUND_ERRORS = ()


def _wrap_error(error: Exception) -> Exception:
    """Maps a PubSub SDK error onto the Plugboard message broker exception hierarchy.

    Args:
        error: The error raised by the PubSub client.

    Returns:
        A `NoMoreDataException` for a deleted topic/subscription, a
        `MessageBrokerPermanentError` for a rejection that will not change on retry, a
        `MessageBrokerTransientError` for a failure worth retrying, otherwise the
        original error.
    """
    if isinstance(error, _NOT_FOUND_ERRORS):
        return NoMoreDataException()
    if isinstance(error, _PERMANENT_ERRORS):
        return MessageBrokerPermanentError(str(error))
    if isinstance(error, _TRANSIENT_ERRORS):
        return MessageBrokerTransientError(str(error))
    return error


class GCPPubSubDataReader(MessageDataReader):
    """Reads data from a Google Cloud PubSub subscription.

    Messages are pulled from the subscription in batches and converted to field
    values. A batch is acknowledged once all of its records have been consumed, so a
    failure before that point leaves the remaining messages for redelivery.

    The PubSub client library is synchronous, so every call is dispatched to a worker
    thread to keep the process event loop free for other components.
    """

    @depends_on_optional("google.cloud.pubsub_v1", extra="gcp-pubsub")
    def __init__(
        self,
        subscription_id: str,
        project_id: _t.Optional[str] = None,
        parse_json: bool = True,
        pull_timeout: float = 30.0,
        **kwargs: _t.Unpack[MessageDataReaderArgsDict],
    ) -> None:
        """Instantiates the `GCPPubSubDataReader`.

        Args:
            subscription_id: The PubSub subscription ID.
            project_id: Optional; The GCP project ID. Falls back to
                `GCP_PUBSUB_PROJECT_ID`.
            parse_json: Whether to parse message data as JSON.
            pull_timeout: Seconds to wait for a `pull()` call to return.
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        project_id = resolve_argument(
            project_id,
            DI.settings.resolve_sync().gcp_pubsub.project_id,
            "project_id",
            "GCP_PUBSUB_PROJECT_ID",
        )
        kwargs.setdefault("topic", f"{project_id}/{subscription_id}")
        super().__init__(**kwargs)
        self._project_id = project_id
        self._subscription_id = subscription_id
        self._subscription_path = f"projects/{project_id}/subscriptions/{subscription_id}"
        self._parse_json = parse_json
        self._pull_timeout = pull_timeout
        self._subscriber: _t.Optional[pubsub_v1.SubscriberClient] = None

    async def _connect(self) -> None:
        """Creates a PubSub subscriber client."""
        self._subscriber = await asyncio.to_thread(pubsub_v1.SubscriberClient)

    async def _disconnect(self) -> None:
        """Closes the PubSub subscriber client."""
        if self._subscriber is not None:
            subscriber = self._subscriber
            self._subscriber = None
            await asyncio.to_thread(subscriber.close)

    async def _receive(self) -> list[_t.Any]:
        """Pulls a batch of messages from the PubSub subscription.

        Returns:
            A list of PubSub `ReceivedMessage` objects, empty if the pull timed out.

        Raises:
            NoMoreDataException: If the subscription no longer exists.
            MessageBrokerError: If the pull failed for a retryable or permanent reason.
        """
        if self._subscriber is None:
            raise MessageBrokerConnectionError("Subscriber client is not connected")
        request = {
            "subscription": self._subscription_path,
            "max_messages": self._chunk_size or 10,
        }
        try:
            response = await asyncio.to_thread(
                self._subscriber.pull, request=request, timeout=self._pull_timeout
            )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error
        return list(response.received_messages)

    async def _convert(self, data: list[_t.Any]) -> dict[str, deque]:
        """Converts PubSub messages to a field buffer.

        Args:
            data: A list of `ReceivedMessage` objects.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for msg_wrapper in data:
            payload = msg_wrapper.message.data
            if self._parse_json:
                record = json.loads(payload.decode("utf-8"))
            else:
                record = {"data": payload}
            for field in self.io.outputs:
                converted[field].append(record.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        """Acknowledges processed PubSub messages.

        Args:
            messages: The `ReceivedMessage` objects to acknowledge.

        Raises:
            MessageBrokerConnectionError: If the client is not connected.
            MessageBrokerError: If the acknowledgment failed.
        """
        if self._subscriber is None:
            raise MessageBrokerConnectionError("Subscriber client is not connected")
        ack_ids = [msg_wrapper.ack_id for msg_wrapper in messages]
        request = {"subscription": self._subscription_path, "ack_ids": ack_ids}
        try:
            await asyncio.to_thread(self._subscriber.acknowledge, request=request)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error


class GCPPubSubDataWriter(MessageDataWriter):
    """Writes data to a Google Cloud PubSub topic.

    Field data is converted to JSON-encoded messages and published to the specified
    topic. The PubSub client library is synchronous, so publishing and waiting for
    broker confirmation run in a worker thread.
    """

    @depends_on_optional("google.cloud.pubsub_v1", extra="gcp-pubsub")
    def __init__(
        self,
        topic_id: str,
        project_id: _t.Optional[str] = None,
        parse_json: bool = True,
        publish_timeout: float = 60.0,
        **kwargs: _t.Unpack[MessageDataWriterArgsDict],
    ) -> None:
        """Instantiates the `GCPPubSubDataWriter`.

        Args:
            topic_id: The PubSub topic ID.
            project_id: Optional; The GCP project ID. Falls back to
                `GCP_PUBSUB_PROJECT_ID`.
            parse_json: Whether to encode message data as JSON.
            publish_timeout: Seconds to wait for each publish to be confirmed.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        project_id = resolve_argument(
            project_id,
            DI.settings.resolve_sync().gcp_pubsub.project_id,
            "project_id",
            "GCP_PUBSUB_PROJECT_ID",
        )
        kwargs.setdefault("topic", f"{project_id}/{topic_id}")
        super().__init__(**kwargs)
        self._project_id = project_id
        self._topic_id = topic_id
        self._topic_path = f"projects/{project_id}/topics/{topic_id}"
        self._parse_json = parse_json
        self._publish_timeout = publish_timeout
        self._publisher: _t.Optional[pubsub_v1.PublisherClient] = None

    async def _connect(self) -> None:
        """Creates a PubSub publisher client."""
        self._publisher = await asyncio.to_thread(pubsub_v1.PublisherClient)

    async def _disconnect(self) -> None:
        """Stops the PubSub publisher, flushing any queued messages and closing its channel.

        Raises:
            MessageBrokerError: If the publisher fails to stop.
        """
        if self._publisher is not None:
            publisher = self._publisher
            self._publisher = None
            try:
                await asyncio.to_thread(publisher.stop)
            except Exception as error:  # noqa: BLE001
                raise _wrap_error(error) from error

    async def _send(self, messages: list[_t.Any]) -> None:
        """Publishes messages to the PubSub topic and waits for broker confirmation.

        Args:
            messages: A list of bytes objects to publish.

        Raises:
            MessageBrokerConnectionError: If the client is not connected.
            MessageBrokerError: If a publish failed or was not confirmed in time.
        """
        if self._publisher is None:
            raise MessageBrokerConnectionError("Publisher client is not connected")
        publisher = self._publisher

        def _publish() -> None:
            futures = [publisher.publish(self._topic_path, data=msg_data) for msg_data in messages]
            # The publisher batches internally; each future resolves once the broker
            # has accepted that message.
            for future in futures:
                future.result(timeout=self._publish_timeout)

        try:
            await asyncio.to_thread(_publish)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded bytes messages.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of bytes objects ready to publish.
        """
        return encode_records_bytes(data, self._parse_json)
