"""Provides `AWSSQSDataReader` and `AWSSNSDataWriter` for AWS SQS/SNS messaging."""

from __future__ import annotations

from collections import deque
import contextlib
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
    encode_records,
)
from plugboard.utils import DI, depends_on_optional
from plugboard.utils.settings import resolve_argument


try:
    from aiobotocore.session import get_session
    from botocore.exceptions import BotoCoreError, ClientError

    _CLIENT_ERRORS: tuple[type[Exception], ...] = (ClientError,)
    # BotoCoreError covers transport failures: timeouts, DNS and connection resets.
    _TRANSPORT_ERRORS: tuple[type[Exception], ...] = (BotoCoreError,)
except ImportError:  # pragma: no cover
    # With the extra not installed, `depends_on_optional` blocks construction and
    # classification is moot: `isinstance(error, ())` never matches.
    _CLIENT_ERRORS = ()
    _TRANSPORT_ERRORS = ()


# SQS returns at most this many messages per `ReceiveMessage` call.
_SQS_MAX_MESSAGES = 10
# SQS accepts at most this many entries per `DeleteMessageBatch` call.
_SQS_MAX_BATCH = 10

_PERMANENT_CODES = frozenset(
    {
        "AccessDenied",
        "AuthorizationError",
        "IncompleteSignature",
        "InvalidAddress",
        "InvalidClientTokenId",
        "InvalidMessageContents",
        "MalformedXML",
        "MessageNotInflight",
        "ReceiptHandleIsInvalid",
        "SignatureDoesNotMatch",
        "UnrecognizedClientException",
    }
)

_TRANSIENT_CODES = frozenset(
    {
        "InternalError",
        "RequestExpired",
        "RequestThrottled",
        "ServiceUnavailable",
        "ThrottledException",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)

_MISSING_RESOURCE_CODES = frozenset(
    {
        "AWS.SimpleQueueService.NonExistentQueue",
        "NotFound",
        "QueueDoesNotExist",
        "NoSuchTopic",
    }
)


def _error_code(error: Exception) -> _t.Optional[str]:
    """Extracts the AWS error code from a client error, if it has one."""
    if not isinstance(error, _CLIENT_ERRORS):
        return None
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    return response.get("Error", {}).get("Code")


def _wrap_error(error: Exception, *, exhausted: bool = False) -> Exception:
    """Maps an AWS SDK error onto the Plugboard message broker exception hierarchy.

    Args:
        error: The error raised by the AWS client.
        exhausted: Whether a missing queue/topic should be reported as an exhausted
            source. Only meaningful for a reader: a writer cannot recover from a
            missing topic, so it is a permanent failure there.

    Returns:
        A `NoMoreDataException` for a deleted queue (readers only), a
        `MessageBrokerPermanentError` for a rejection that will not change on retry, a
        `MessageBrokerTransientError` for a failure worth retrying, otherwise the
        original error.
    """
    code = _error_code(error)
    if code in _MISSING_RESOURCE_CODES:
        return NoMoreDataException() if exhausted else MessageBrokerPermanentError(str(error))
    if code in _PERMANENT_CODES:
        return MessageBrokerPermanentError(str(error))
    if code in _TRANSIENT_CODES or isinstance(error, _TRANSPORT_ERRORS):
        return MessageBrokerTransientError(str(error))
    return error


class AWSSQSDataReader(MessageDataReader):
    """Reads data from an AWS SQS queue.

    Messages are received using long polling and converted to field values.
    Acknowledging a batch deletes its messages from the queue, which happens once all
    of the batch's records have been consumed, so a failure before that point leaves
    the remaining messages visible for redelivery.
    """

    @depends_on_optional("aiobotocore", extra="aws-messaging")
    def __init__(
        self,
        queue_url: str,
        region: _t.Optional[str] = None,
        parse_json: bool = True,
        wait_time_seconds: int = 20,
        **kwargs: _t.Unpack[MessageDataReaderArgsDict],
    ) -> None:
        """Instantiates the `AWSSQSDataReader`.

        Args:
            queue_url: The SQS queue URL.
            region: Optional; The AWS region. Falls back to `AWS_REGION`.
            parse_json: Whether to parse message bodies as JSON.
            wait_time_seconds: Long-polling wait time in seconds (max 20).
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        region = resolve_argument(
            region, DI.settings.resolve_sync().aws.region, "region", "AWS_REGION"
        )
        kwargs.setdefault("topic", queue_url)
        super().__init__(**kwargs)
        if self._chunk_size and self._chunk_size > _SQS_MAX_MESSAGES:
            self._logger.warning(
                "SQS returns at most 10 messages per receive, so chunk_size is capped",
                chunk_size=self._chunk_size,
                max_messages=_SQS_MAX_MESSAGES,
            )
        self._queue_url = queue_url
        self._region = region
        self._parse_json = parse_json
        self._wait_time_seconds = wait_time_seconds
        self._client: _t.Any = None
        self._exit_stack: _t.Optional[contextlib.AsyncExitStack] = None

    async def _connect(self) -> None:
        """Creates an SQS client."""
        self._exit_stack = contextlib.AsyncExitStack()
        self._client = await self._exit_stack.enter_async_context(
            get_session().create_client("sqs", region_name=self._region)
        )

    async def _disconnect(self) -> None:
        """Closes the SQS client."""
        if self._exit_stack is not None:
            exit_stack = self._exit_stack
            self._exit_stack = None
            self._client = None
            await exit_stack.aclose()

    async def _receive(self) -> list[_t.Any]:
        """Receives a batch of messages from the SQS queue using long polling.

        Returns:
            A list of SQS message dicts, empty if the long poll timed out.

        Raises:
            NoMoreDataException: If the queue no longer exists.
            MessageBrokerError: If the receive failed for a retryable or permanent reason.
        """
        if self._client is None:
            raise MessageBrokerConnectionError("SQS client is not connected")
        request = {
            "QueueUrl": self._queue_url,
            "MaxNumberOfMessages": min(self._chunk_size or _SQS_MAX_MESSAGES, _SQS_MAX_MESSAGES),
            "WaitTimeSeconds": self._wait_time_seconds,
        }
        try:
            response = await self._client.receive_message(**request)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error, exhausted=True) from error
        return response.get("Messages", [])

    async def _convert(self, data: list[_t.Any]) -> dict[str, deque]:
        """Converts SQS messages to a field buffer.

        Args:
            data: A list of SQS message dicts.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for msg in data:
            body = msg.get("Body", "")
            if self._parse_json:
                record = json.loads(body)
            else:
                record = {"data": body}
            for field in self.io.outputs:
                converted[field].append(record.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        """Deletes processed messages from the SQS queue.

        Deletes run in batches of up to 10, the SQS batch limit.

        Args:
            messages: The SQS message dicts to delete.

        Raises:
            MessageBrokerConnectionError: If the client is not connected.
            MessageBrokerTransientError: If any message could not be deleted.
        """
        if self._client is None:
            raise MessageBrokerConnectionError("SQS client is not connected")
        for start in range(0, len(messages), _SQS_MAX_BATCH):
            entries = [
                {"Id": str(index), "ReceiptHandle": msg["ReceiptHandle"]}
                for index, msg in enumerate(messages[start : start + _SQS_MAX_BATCH])
                if msg.get("ReceiptHandle")
            ]
            if not entries:
                continue
            try:
                response = await self._client.delete_message_batch(
                    QueueUrl=self._queue_url, DeleteMessageRequests=entries
                )
            except Exception as error:  # noqa: BLE001
                raise _wrap_error(error) from error
            if errors := response.get("Errors"):
                # A partially failed delete leaves those messages visible for
                # redelivery, so report it rather than pretending the batch is done.
                raise MessageBrokerTransientError(
                    f"Failed to delete {len(errors)} SQS message(s): {errors}"
                )


class AWSSNSDataWriter(MessageDataWriter):
    """Writes data to an AWS SNS topic.

    Field data is converted to JSON-encoded messages and published to the specified
    topic. SNS has no batch publish API for standard topics, so records are published
    one at a time per send.
    """

    @depends_on_optional("aiobotocore", extra="aws-messaging")
    def __init__(
        self,
        topic_arn: str,
        region: _t.Optional[str] = None,
        parse_json: bool = True,
        **kwargs: _t.Unpack[MessageDataWriterArgsDict],
    ) -> None:
        """Instantiates the `AWSSNSDataWriter`.

        Args:
            topic_arn: The SNS topic ARN.
            region: Optional; The AWS region. Falls back to `AWS_REGION`.
            parse_json: Whether to encode message data as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        region = resolve_argument(
            region, DI.settings.resolve_sync().aws.region, "region", "AWS_REGION"
        )
        kwargs.setdefault("topic", topic_arn)
        super().__init__(**kwargs)
        self._topic_arn = topic_arn
        self._region = region
        self._parse_json = parse_json
        self._client: _t.Any = None
        self._exit_stack: _t.Optional[contextlib.AsyncExitStack] = None

    async def _connect(self) -> None:
        """Creates an SNS client."""
        self._exit_stack = contextlib.AsyncExitStack()
        self._client = await self._exit_stack.enter_async_context(
            get_session().create_client("sns", region_name=self._region)
        )

    async def _disconnect(self) -> None:
        """Closes the SNS client."""
        if self._exit_stack is not None:
            exit_stack = self._exit_stack
            self._exit_stack = None
            self._client = None
            await exit_stack.aclose()

    async def _send(self, messages: list[_t.Any]) -> None:
        """Publishes messages to the SNS topic.

        Args:
            messages: A list of message strings to publish.

        Raises:
            MessageBrokerConnectionError: If the client is not connected.
            MessageBrokerError: If a publish failed.
        """
        if self._client is None:
            raise MessageBrokerConnectionError("SNS client is not connected")
        for msg_data in messages:
            try:
                await self._client.publish(TopicArn=self._topic_arn, Message=msg_data)
            except Exception as error:  # noqa: BLE001
                raise _wrap_error(error) from error

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded message strings.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of message strings ready to publish.
        """
        return encode_records(data, self._parse_json)
