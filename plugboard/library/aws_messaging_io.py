"""Provides `AWSSQSDataReader` and `AWSSNSDataWriter` for AWS SQS/SNS messaging."""

from __future__ import annotations

from collections import deque
import json
import typing as _t

from plugboard.exceptions import NoMoreDataException
from plugboard.library.message_reader import MessageDataReader, MessageDataReaderArgsDict
from plugboard.library.message_writer import MessageDataWriter, MessageDataWriterArgsDict
from plugboard.utils import depends_on_optional


try:
    import aioboto3
except ImportError:  # pragma: no cover
    pass


class AWSSQSDataReaderArgsDict(MessageDataReaderArgsDict):
    """Specification of the `AWSSQSDataReader` constructor arguments.

    Attributes:
        queue_url: The SQS queue URL.
        region: The AWS region.
        parse_json: Whether to parse message bodies as JSON.
        wait_time_seconds: Long-polling wait time in seconds.
    """

    pass


class AWSSNSDataWriterArgsDict(MessageDataWriterArgsDict):
    """Specification of the `AWSSNSDataWriter` constructor arguments.

    Attributes:
        topic_arn: The SNS topic ARN.
        region: The AWS region.
        parse_json: Whether to encode message data as JSON.
    """

    pass


class AWSSQSDataReader(MessageDataReader):
    """Reads data from an AWS SQS queue.

    Messages are received from the queue using long-polling and converted
    to field values. Messages are deleted from the queue after processing
    (acknowledgment).
    """

    @depends_on_optional("aioboto3", extra="aws-messaging")
    def __init__(
        self,
        queue_url: str,
        region: str,
        parse_json: bool = True,
        wait_time_seconds: int = 20,
        **kwargs: _t.Unpack[AWSSQSDataReaderArgsDict],
    ) -> None:
        """Instantiates the `AWSSQSDataReader`.

        Args:
            queue_url: The SQS queue URL.
            region: The AWS region.
            parse_json: Whether to parse message bodies as JSON.
            wait_time_seconds: Long-polling wait time in seconds (max 20).
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        kwargs.setdefault("topic", queue_url)
        super().__init__(**kwargs)
        self._queue_url = queue_url
        self._region = region
        self._parse_json = parse_json
        self._wait_time_seconds = wait_time_seconds
        self._session: _t.Any = None
        self._client: _t.Any = None

    async def _connect(self) -> None:
        """Creates an SQS client session."""
        self._session = aioboto3.Session()
        self._client_ctx = self._session.client("sqs", region_name=self._region)
        self._client = await self._client_ctx.__aenter__()

    async def _disconnect(self) -> None:
        """Closes the SQS client session."""
        if self._client is not None:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception:  # noqa: S110
                pass
            self._client = None
            self._session = None

    async def _receive(self) -> list[_t.Any]:
        """Receives a batch of messages from the SQS queue.

        Returns:
            A list of SQS message dicts.

        Raises:
            NoMoreDataException: If the queue does not exist.
        """
        if self._client is None:
            raise RuntimeError("SQS client not initialized")
        max_messages = min(self._chunk_size or 10, 10)  # SQS max is 10
        try:
            response = await self._client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=self._wait_time_seconds,
            )
        except Exception as e:
            if "QueueDoesNotExist" in str(type(e).__name__) or "NonExistentQueue" in str(e):
                raise NoMoreDataException from e
            raise
        return response.get("Messages", [])

    async def _convert(self, messages: list[_t.Any]) -> dict[str, deque]:
        """Converts SQS messages to a field buffer.

        Args:
            messages: A list of SQS message dicts.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for msg in messages:
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

        Args:
            messages: The SQS message dicts to delete.
        """
        if self._client is None:
            raise RuntimeError("SQS client not initialized")
        for msg in messages:
            receipt_handle = msg.get("ReceiptHandle")
            if receipt_handle:
                await self._client.delete_message(
                    QueueUrl=self._queue_url, ReceiptHandle=receipt_handle
                )


class AWSSNSDataWriter(MessageDataWriter):
    """Writes data to an AWS SNS topic.

    Field data is converted to JSON-encoded messages and published
    to the specified SNS topic.
    """

    @depends_on_optional("aioboto3", extra="aws-messaging")
    def __init__(
        self,
        topic_arn: str,
        region: str,
        parse_json: bool = True,
        **kwargs: _t.Unpack[AWSSNSDataWriterArgsDict],
    ) -> None:
        """Instantiates the `AWSSNSDataWriter`.

        Args:
            topic_arn: The SNS topic ARN.
            region: The AWS region.
            parse_json: Whether to encode message data as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        kwargs.setdefault("topic", topic_arn)
        super().__init__(**kwargs)
        self._topic_arn = topic_arn
        self._region = region
        self._parse_json = parse_json
        self._session: _t.Any = None
        self._client: _t.Any = None

    async def _connect(self) -> None:
        """Creates an SNS client session."""
        self._session = aioboto3.Session()
        self._client_ctx = self._session.client("sns", region_name=self._region)
        self._client = await self._client_ctx.__aenter__()

    async def _disconnect(self) -> None:
        """Closes the SNS client session."""
        if self._client is not None:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception:  # noqa: S110
                pass
            self._client = None
            self._session = None

    async def _send(self, messages: list[_t.Any]) -> None:
        """Publishes messages to the SNS topic.

        Args:
            messages: A list of message strings to publish.
        """
        if self._client is None:
            raise RuntimeError("SNS client not initialized")
        for msg_data in messages:
            await self._client.publish(
                TopicArn=self._topic_arn,
                Message=msg_data,
            )

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded message strings.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of message strings ready to publish.
        """
        completed_rows = min(len(d) for d in data.values()) if data else 0
        messages: list[str] = []
        for i in range(completed_rows):
            record = {field: data[field][i] for field in data}
            if self._parse_json:
                messages.append(json.dumps(record))
            else:
                first_field = next(iter(record.values()))
                messages.append(str(first_field))
        return messages
