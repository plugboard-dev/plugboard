"""Provides `KafkaDataReader` and `KafkaDataWriter` for Apache Kafka messaging."""

from __future__ import annotations

from collections import deque
import json
import typing as _t

from plugboard.exceptions import NoMoreDataException
from plugboard.library.message_reader import MessageDataReader, MessageDataReaderArgsDict
from plugboard.library.message_writer import MessageDataWriter, MessageDataWriterArgsDict
from plugboard.utils import depends_on_optional


try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except ImportError:  # pragma: no cover
    pass


class KafkaDataReaderArgsDict(MessageDataReaderArgsDict):
    """Specification of the `KafkaDataReader` constructor arguments.

    Attributes:
        bootstrap_servers: Kafka broker address(es).
        group_id: Consumer group ID.
        parse_json: Whether to parse message values as JSON.
    """

    pass


class KafkaDataWriterArgsDict(MessageDataWriterArgsDict):
    """Specification of the `KafkaDataWriter` constructor arguments.

    Attributes:
        bootstrap_servers: Kafka broker address(es).
        parse_json: Whether to encode message values as JSON.
    """

    pass


class KafkaDataReader(MessageDataReader):
    """Reads data from an Apache Kafka topic.

    Messages are consumed from the topic using a consumer group and converted
    to field values. Offsets are committed after processing (acknowledgment).
    """

    @depends_on_optional("aiokafka", extra="kafka")
    def __init__(
        self,
        bootstrap_servers: str | list[str],
        group_id: str,
        parse_json: bool = True,
        **kwargs: _t.Unpack[KafkaDataReaderArgsDict],
    ) -> None:
        """Instantiates the `KafkaDataReader`.

        Args:
            bootstrap_servers: Kafka broker address(es) (e.g. `"localhost:9092"`).
            group_id: Consumer group ID.
            parse_json: Whether to parse message values as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataReader`][plugboard.library.MessageDataReader].
        """
        super().__init__(**kwargs)
        if isinstance(bootstrap_servers, str):
            bootstrap_servers = [bootstrap_servers]
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._parse_json = parse_json
        self._consumer: _t.Optional[AIOKafkaConsumer] = None

    async def _connect(self) -> None:
        """Creates and starts a Kafka consumer."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_records=self._chunk_size or 10,
        )
        await self._consumer.start()

    async def _disconnect(self) -> None:
        """Stops and closes the Kafka consumer."""
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def _receive(self) -> list[_t.Any]:
        """Receives a batch of messages from the Kafka topic.

        Returns:
            A list of Kafka `ConsumerRecord` objects.

        Raises:
            NoMoreDataException: If the consumer has been closed.
        """
        if self._consumer is None:
            raise RuntimeError("Kafka consumer not initialized")
        max_messages = self._chunk_size or 10
        # Use getmany to fetch a batch with timeout
        data = await self._consumer.getmany(timeout_ms=30000, max_records=max_messages)
        messages: list[_t.Any] = []
        for _tp, records in data.items():
            messages.extend(records)
        if not messages:
            raise NoMoreDataException
        return messages[:max_messages]

    async def _convert(self, messages: list[_t.Any]) -> dict[str, deque]:
        """Converts Kafka messages to a field buffer.

        Args:
            messages: A list of `ConsumerRecord` objects.

        Returns:
            A dictionary mapping field names to deques of field values.
        """
        converted: dict[str, deque] = {field: deque() for field in self.io.outputs}
        for record in messages:
            value = record.value
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            if self._parse_json:
                record_data = json.loads(value)
            else:
                record_data = {"data": value}
            for field in self.io.outputs:
                converted[field].append(record_data.get(field))
        return converted

    async def _ack(self, messages: list[_t.Any]) -> None:
        """Commits offsets for processed Kafka messages.

        Args:
            messages: The `ConsumerRecord` objects to acknowledge.
        """
        if self._consumer is None:
            raise RuntimeError("Kafka consumer not initialized")
        await self._consumer.commit()


class KafkaDataWriter(MessageDataWriter):
    """Writes data to an Apache Kafka topic.

    Field data is converted to JSON-encoded messages and produced
    to the specified Kafka topic.
    """

    @depends_on_optional("aiokafka", extra="kafka")
    def __init__(
        self,
        bootstrap_servers: str | list[str],
        parse_json: bool = True,
        **kwargs: _t.Unpack[KafkaDataWriterArgsDict],
    ) -> None:
        """Instantiates the `KafkaDataWriter`.

        Args:
            bootstrap_servers: Kafka broker address(es) (e.g. `"localhost:9092"`).
            parse_json: Whether to encode message values as JSON.
            **kwargs: Additional keyword arguments for
                [`MessageDataWriter`][plugboard.library.MessageDataWriter].
        """
        super().__init__(**kwargs)
        if isinstance(bootstrap_servers, str):
            bootstrap_servers = [bootstrap_servers]
        self._bootstrap_servers = bootstrap_servers
        self._parse_json = parse_json
        self._producer: _t.Optional[AIOKafkaProducer] = None

    async def _connect(self) -> None:
        """Creates and starts a Kafka producer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
        )
        await self._producer.start()

    async def _disconnect(self) -> None:
        """Stops and closes the Kafka producer."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def _send(self, messages: list[_t.Any]) -> None:
        """Sends messages to the Kafka topic.

        Args:
            messages: A list of bytes objects to send.
        """
        if self._producer is None:
            raise RuntimeError("Kafka producer not initialized")
        for msg_data in messages:
            await self._producer.send_and_wait(self._topic, value=msg_data)

    async def _convert(self, data: dict[str, deque]) -> list[_t.Any]:
        """Converts field buffer data to JSON-encoded bytes messages.

        Args:
            data: A dictionary mapping field names to deques of field values.

        Returns:
            A list of bytes objects ready to send.
        """
        completed_rows = min(len(d) for d in data.values()) if data else 0
        messages: list[bytes] = []
        for i in range(completed_rows):
            record = {field: data[field][i] for field in data}
            if self._parse_json:
                messages.append(json.dumps(record).encode("utf-8"))
            else:
                first_field = next(iter(record.values()))
                messages.append(
                    first_field if isinstance(first_field, bytes) else str(first_field).encode()
                )
        return messages
