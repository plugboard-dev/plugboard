# Proposal: MessageDataReader and MessageDataWriter Base Classes

## Issue Reference

[Issue #102: feat: Base component for external communication](https://github.com/plugboard-dev/plugboard/issues/102)

## Summary

Develop `MessageDataReader` and `MessageDataWriter` abstract base classes that provide common logic for reading from and writing to pub/sub message broker infrastructure. These are analogous to the existing `DataReader` and `DataWriter` components (which handle chunking/transforming for file access), but focused on message broker communication — including connection management, reconnection, retries, and message acknowledgment.

Three concrete implementations will be provided:
1. **Google Cloud PubSub** (`GCPPubSubDataReader` / `GCPPubSubDataWriter`)
2. **AWS SNS/SQS** (`AWSSNSQSDataReader` / `AWSSQSDataWriter`)
3. **Apache Kafka** (`KafkaDataReader` / `KafkaDataWriter`)

---

## Design Rationale

### Why not extend `DataReader`/`DataWriter`?

The existing `DataReader`/`DataWriter` classes are designed for finite data sources (files, databases) where:
- `_fetch()` raises `NoMoreDataException` when data is exhausted
- Data is read in chunks until the source is depleted
- No connection lifecycle management is needed (connections are per-query)

Message brokers have fundamentally different semantics:
- Data arrives continuously (no natural "end of data")
- Connections are long-lived and must be managed (connect, reconnect, disconnect)
- Messages require acknowledgment after processing
- Transient failures require retry with exponential backoff

Therefore, `MessageDataReader`/`MessageDataWriter` will be standalone `Component` subclasses that follow a *similar* pattern to `DataReader`/`DataWriter` (field-based IO, chunking, buffering) but with message-broker-specific lifecycle management.

### Relationship to existing patterns

| Pattern | Base Class | Handles | Subclasses implement |
|---------|-----------|---------|---------------------|
| File I/O | `DataReader`/`DataWriter` | Chunking, buffering, field IO | `_fetch()`, `_convert()`, `_save()` |
| WebSocket | `WebsocketBase` | Connection lifecycle, reconnection | `step()` for read/write |
| **Message Broker** | `MessageDataReader`/`MessageDataWriter` | Connection lifecycle, reconnection, retry, chunking, buffering, acknowledgment | `_connect()`, `_disconnect()`, `_receive()`/`_send()`, `_convert()`, `_ack()` |

---

## Interface Design

### `MessageDataReader`

```python
class MessageDataReader(Component, ABC):
    """Abstract base class for reading data from a pub/sub message broker.

    Provides connection management, reconnection with exponential backoff,
    retry logic, message acknowledgment, and chunked/buffered reading
    analogous to `DataReader`.

    Subclasses must implement broker-specific methods for connecting,
    receiving messages, converting messages to field buffers, and
    acknowledging processed messages.
    """

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        topic: str,
        subscription_id: str | None = None,
        chunk_size: int | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        **kwargs: Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiate the `MessageDataReader`.

        Args:
            field_names: The names of the fields to extract from messages.
            topic: The topic/queue to read from.
            subscription_id: Optional; A subscription ID (required for some brokers like GCP PubSub).
            chunk_size: Optional; Number of messages to fetch per batch.
            max_retries: Maximum number of retry attempts for transient failures.
            retry_base_delay: Base delay in seconds for exponential backoff.
            retry_max_delay: Maximum delay in seconds for exponential backoff.
            **kwargs: Additional keyword arguments for `Component`.
        """
```

#### Abstract methods (implemented by subclasses):

| Method | Signature | Description |
|--------|-----------|-------------|
| `_connect` | `async def _connect(self) -> None` | Establish connection to the message broker. |
| `_disconnect` | `async def _disconnect(self) -> None` | Close the connection to the message broker. |
| `_receive` | `async def _receive(self) -> list[Any]` | Receive a batch of raw messages from the broker. Should block until at least one message is available or a timeout occurs. Return empty list on timeout. |
| `_convert` | `async def _convert(self, messages: list[Any]) -> dict[str, deque]` | Convert raw messages into a `dict[str, deque]` field buffer. |
| `_ack` | `async def _ack(self, messages: list[Any]) -> None` | Acknowledge successful processing of messages. |

#### Concrete methods (provided by base class):

| Method | Description |
|--------|-------------|
| `init()` | Calls `_connect()` with retry logic. Pre-fetches first batch. |
| `step()` | Consumes one record from the buffer. Fetches next batch if buffer empty. Calls `_ack()` on processed messages. |
| `destroy()` | Calls `_disconnect()` to clean up broker connection. |
| `_receive_with_retry()` | Wraps `_receive()` with exponential backoff retry and automatic reconnection. |

### `MessageDataWriter`

```python
class MessageDataWriter(Component, ABC):
    """Abstract base class for writing data to a pub/sub message broker.

    Provides connection management, reconnection with exponential backoff,
    retry logic, and chunked/buffered writing analogous to `DataWriter`.

    Subclasses must implement broker-specific methods for connecting,
    sending messages, converting field data to messages, and
    broker-specific message formatting.
    """

    io = IOController()

    def __init__(
        self,
        field_names: list[str],
        topic: str,
        chunk_size: int | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        **kwargs: Unpack[ComponentArgsDict],
    ) -> None:
        """Instantiate the `MessageDataWriter`.

        Args:
            field_names: The names of the fields to include in messages.
            topic: The topic/queue to write to.
            chunk_size: Optional; Number of records to batch into a single message.
            max_retries: Maximum number of retry attempts for transient failures.
            retry_base_delay: Base delay in seconds for exponential backoff.
            retry_max_delay: Maximum delay in seconds for exponential backoff.
            **kwargs: Additional keyword arguments for `Component`.
        """
```

#### Abstract methods (implemented by subclasses):

| Method | Signature | Description |
|--------|-----------|-------------|
| `_connect` | `async def _connect(self) -> None` | Establish connection to the message broker. |
| `_disconnect` | `async def _disconnect(self) -> None` | Close the connection to the message broker. |
| `_send` | `async def _send(self, messages: list[Any]) -> None` | Send a batch of messages to the broker. |
| `_convert` | `async def _convert(self, data: dict[str, deque]) -> list[Any]` | Convert field buffer data into broker-specific message format. |

#### Concrete methods (provided by base class):

| Method | Description |
|--------|-------------|
| `init()` | Calls `_connect()` with retry logic. |
| `step()` | Buffers input fields. Triggers `_send()` when `chunk_size` reached. |
| `run()` | Runs step loop to completion, then flushes remaining buffered data. |
| `destroy()` | Calls `_disconnect()` to clean up broker connection. |
| `_send_with_retry()` | Wraps `_send()` with exponential backoff retry and automatic reconnection. |

---

## Connection Management & Retry Strategy

The base classes provide robust connection management:

### Connection lifecycle

```
init() → _connect() [with retry] → ready for step()
step() → _receive_with_retry() / _send_with_retry() → process messages
destroy() → _disconnect()
```

### Reconnection with exponential backoff

```python
async def _receive_with_retry(self) -> list[Any]:
    """Receives messages with retry and exponential backoff."""
    last_exception = None
    for attempt in range(self._max_retries + 1):
        try:
            return await self._receive()
        except TransientError as e:
            last_exception = e
            if attempt < self._max_retries:
                delay = min(
                    self._retry_base_delay * (2 ** attempt),
                    self._retry_max_delay,
                )
                self._logger.warning(
                    "Transient error receiving messages, retrying",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                # Attempt reconnection before retry
                await self._reconnect()
    raise last_exception  # type: ignore[misc]
```

### Reconnection strategy

```python
async def _reconnect(self) -> None:
    """Attempts to reconnect to the message broker."""
    self._logger.info("Attempting reconnection to message broker")
    try:
        await self._disconnect()
    except Exception:
        pass  # Best-effort disconnect
    await self._connect()
    self._logger.info("Reconnected to message broker")
```

---

## Concrete Implementations

### 1. Google Cloud PubSub

**Dependencies**: `google-cloud-pubsub` (added as optional dependency `gcp-pubsub`)

#### `GCPPubSubDataReader`

```python
class GCPPubSubDataReader(MessageDataReader):
    """Reads data from Google Cloud PubSub subscription."""

    def __init__(
        self,
        project_id: str,
        subscription_id: str,
        parse_json: bool = True,
        **kwargs: Unpack[MessageDataReaderArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create AsyncSubscriberClient
        # Subscribe to subscription

    async def _disconnect(self) -> None:
        # Close subscriber client

    async def _receive(self) -> list[Any]:
        # Pull batch of messages (up to chunk_size)
        # Return list of PubSubMessage

    async def _convert(self, messages: list[Any]) -> dict[str, deque]:
        # Parse message data (JSON or raw bytes)
        # Extract fields into dict[str, deque]

    async def _ack(self, messages: list[Any]) -> None:
        # Acknowledge messages via subscriber
```

#### `GCPPubSubDataWriter`

```python
class GCPPubSubDataWriter(MessageDataWriter):
    """Writes data to Google Cloud PubSub topic."""

    def __init__(
        self,
        project_id: str,
        topic_id: str,
        parse_json: bool = True,
        **kwargs: Unpack[MessageDataWriterArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create AsyncPublisherClient

    async def _disconnect(self) -> None:
        # Close publisher client

    async def _send(self, messages: list[Any]) -> None:
        # Publish messages to topic

    async def _convert(self, data: dict[str, deque]) -> list[Any]:
        # Convert field data to JSON-encoded bytes
```

### 2. AWS SNS/SQS

**Dependencies**: `aioboto3` or `aws-sdk-pandas` (added as optional dependency `aws-messaging`)

> **Note**: AWS uses SQS for receiving (queue-based) and SNS for publishing (topic-based). The reader uses SQS; the writer can use either SNS (pub/sub) or SQS (queue). We'll implement both.

#### `AWSSQSDataReader`

```python
class AWSSQSDataReader(MessageDataReader):
    """Reads data from AWS SQS queue."""

    def __init__(
        self,
        queue_url: str,
        region: str,
        parse_json: bool = True,
        wait_time_seconds: int = 20,  # Long polling
        **kwargs: Unpack[MessageDataReaderArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create aioboto3 SQS client

    async def _disconnect(self) -> None:
        # Close session

    async def _receive(self) -> list[Any]:
        # ReceiveMessage with MaxNumberOfMessages=chunk_size
        # Long-polling with WaitTimeSeconds

    async def _convert(self, messages: list[Any]) -> dict[str, deque]:
        # Parse message body (JSON)
        # Extract fields

    async def _ack(self, messages: list[Any]) -> None:
        # DeleteMessage for each processed message
```

#### `AWSSNSDataWriter`

```python
class AWSSNSDataWriter(MessageDataWriter):
    """Writes data to AWS SNS topic."""

    def __init__(
        self,
        topic_arn: str,
        region: str,
        parse_json: bool = True,
        **kwargs: Unpack[MessageDataWriterArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create aioboto3 SNS client

    async def _disconnect(self) -> None:
        # Close session

    async def _send(self, messages: list[Any]) -> None:
        # Publish each message to SNS topic

    async def _convert(self, data: dict[str, deque]) -> list[Any]:
        # Convert field data to JSON strings
```

### 3. Apache Kafka

**Dependencies**: `aiokafka` (added as optional dependency `kafka`)

#### `KafkaDataReader`

```python
class KafkaDataReader(MessageDataReader):
    """Reads data from Apache Kafka topic."""

    def __init__(
        self,
        bootstrap_servers: str | list[str],
        topic: str,
        group_id: str,
        parse_json: bool = True,
        **kwargs: Unpack[MessageDataReaderArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create AIOKafkaConsumer
        # Subscribe to topic

    async def _disconnect(self) -> None:
        # Stop consumer

    async def _receive(self) -> list[Any]:
        # getmany() with timeout to fetch batch of messages

    async def _convert(self, messages: list[Any]) -> dict[str, deque]:
        # Parse message value (JSON or raw bytes)
        # Extract fields

    async def _ack(self, messages: list[Any]) -> None:
        # Commit offsets for processed messages
```

#### `KafkaDataWriter`

```python
class KafkaDataWriter(MessageDataWriter):
    """Writes data to Apache Kafka topic."""

    def __init__(
        self,
        bootstrap_servers: str | list[str],
        topic: str,
        parse_json: bool = True,
        **kwargs: Unpack[MessageDataWriterArgsSpec],
    ) -> None:
        ...

    async def _connect(self) -> None:
        # Create AIOKafkaProducer

    async def _disconnect(self) -> None:
        # Stop producer

    async def _send(self, messages: list[Any]) -> None:
        # send_and_wait for each message

    async def _convert(self, data: dict[str, deque]) -> list[Any]:
        # Convert field data to JSON-encoded bytes
```

---

## Module Structure

```
plugboard/library/
├── __init__.py                    # Updated exports
├── data_reader.py                 # Existing DataReader
├── data_writer.py                 # Existing DataWriter
├── file_io.py                     # Existing FileReader/FileWriter
├── sql_io.py                      # Existing SQLReader/SQLWriter
├── websocket_io.py                # Existing WebsocketBase/Reader/Writer
├── message_reader.py              # NEW: MessageDataReader base class
├── message_writer.py              # NEW: MessageDataWriter base class
├── gcp_pubsub_io.py              # NEW: GCPPubSubDataReader/Writer
├── aws_messaging_io.py           # NEW: AWSSQSDataReader/Writer, AWSSNSDataWriter
└── kafka_io.py                   # NEW: KafkaDataReader/Writer
```

---

## Settings & Dependency Injection

### Settings additions (`utils/settings.py`)

```python
class _GCPPubSubSettings(BaseSettings):
    project_id: str | None = None
    model_config = SettingsConfigDict(env_prefix="GCP_PUBSUB_")

class _AWSSettings(BaseSettings):
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    model_config = SettingsConfigDict(env_prefix="AWS_")

class _KafkaSettings(BaseSettings):
    bootstrap_servers: str | list[str] | None = None
    model_config = SettingsConfigDict(env_prefix="KAFKA_")
```

### DI additions (`utils/di.py`)

No new DI resources are needed initially — each concrete implementation manages its own client lifecycle via `_connect()`/`_disconnect()`. DI resources can be added later when integrating against real infrastructure.

---

## Optional Dependencies (`pyproject.toml`)

```toml
[project.optional-dependencies]
gcp-pubsub = ["google-cloud-pubsub>=2.25,<3"]
aws-messaging = ["aioboto3>=13.0,<15"]
kafka = ["aiokafka>=0.11,<1"]
```

---

## Testing Strategy

### Unit Tests (no cloud infrastructure required)

For each base class and concrete implementation, we'll create unit tests using mocks:

1. **`tests/unit/test_message_data_reader.py`**:
   - Test `MessageDataReader` base class behavior with a mock implementation
   - Test connection lifecycle (init → connect, destroy → disconnect)
   - Test retry logic with simulated transient failures
   - Test reconnection behavior
   - Test chunked reading and buffering
   - Test message acknowledgment
   - Test field extraction from messages

2. **`tests/unit/test_message_data_writer.py`**:
   - Test `MessageDataWriter` base class behavior with a mock implementation
   - Test connection lifecycle
   - Test retry logic
   - Test chunked writing and buffering
   - Test flush on `run()` completion
   - Test field data conversion to messages

3. **`tests/unit/test_gcp_pubsub_io.py`**:
   - Test `GCPPubSubDataReader`/`Writer` with mocked `google.cloud.pubsub` clients
   - Test connection setup/teardown
   - Test message receive/convert/ack
   - Test message send/convert

4. **`tests/unit/test_aws_messaging_io.py`**:
   - Test `AWSSQSDataReader`/`AWSSNSDataWriter` with mocked `aioboto3` clients
   - Test SQS receive/ack (delete)
   - Test SNS publish
   - Test long-polling configuration

5. **`tests/unit/test_kafka_io.py`**:
   - Test `KafkaDataReader`/`Writer` with mocked `aiokafka` clients
   - Test consumer/producer lifecycle
   - Test message receive/convert/commit
   - Test message send/convert

### Integration Tests (require cloud infrastructure — for later)

Integration tests will be added in `tests/integration/` once cloud infrastructure is set up:
- `tests/integration/test_gcp_pubsub_io.py`
- `tests/integration/test_aws_messaging_io.py`
- `tests/integration/test_kafka_io.py`

### Test patterns

Following existing patterns:
- `pytest.mark.asyncio` for async tests
- Mock classes extending the abstract base (like `MockDataReader` in existing tests)
- `pytest.fixture` for test data
- Parametrized tests for chunk_size variations
- `structlog` for test logging

---

## Implementation Order

1. **Phase 1**: Base classes (`message_reader.py`, `message_writer.py`) + unit tests
2. **Phase 2**: Google Cloud PubSub implementation + unit tests
3. **Phase 3**: AWS SNS/SQS implementation + unit tests
4. **Phase 4**: Kafka implementation + unit tests
5. **Phase 5**: Update `__init__.py` exports, settings, pyproject.toml dependencies
6. **Phase 6**: Integration tests (when cloud infrastructure is available)

---

## Error Handling

### Custom exceptions

```python
class MessageBrokerConnectionError(Exception):
    """Raised when connection to message broker fails."""

class MessageBrokerTransientError(Exception):
    """Raised on transient broker errors (eligible for retry)."""

class MessageBrokerPermanentError(Exception):
    """Raised on permanent broker errors (not eligible for retry)."""
```

### Error classification

Each concrete implementation is responsible for classifying broker-specific errors into these categories. The base class handles retry logic based on these classifications.

---

## Serialization

Messages will be serialized as JSON by default (configurable via `parse_json` flag). This follows the pattern established by `WebsocketReader`/`WebsocketWriter` and ensures interoperability across different broker implementations.

For the `_convert()` method:
- **Reader**: Parse JSON message data → extract named fields → `dict[str, deque]`
- **Writer**: Take `dict[str, deque]` → combine into records → serialize as JSON

---

## Future Enhancements

- Dead-letter queue handling
- Message filtering / schema validation
- Metrics collection (message rates, latencies)
- Schema registry integration (Avro, Protobuf)
- DI-managed broker connections (for connection pooling across components)
- Batch acknowledgment optimizations
