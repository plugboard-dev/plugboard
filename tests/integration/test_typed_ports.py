"""Typed port checks across process initialization and component execution."""

import typing as _t

import msgspec
import pytest

from plugboard.component import Component, IOController as IO
from plugboard.component.port_types import RuntimeValidation
from plugboard.connector import AsyncioConnector, Connector, RayConnector
from plugboard.events import Event
from plugboard.exceptions import ValidationError
from plugboard.process import LocalProcess, Process, RayProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec, Status


class Source(Component):
    """Producer that can violate its declared output contract."""

    io = IO(outputs={"value": list[int]})

    def __init__(self, invalid: bool = False, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._invalid = invalid

    async def step(self) -> None:
        """Emit one payload."""
        self.value = ["wrong"] if self._invalid else [1]


class DynamicSink(Component):
    """Consumer whose port types and policy are declared at instance construction."""

    io = IO(inputs=["value"])
    exports = ["received"]

    def __init__(
        self,
        mode: RuntimeValidation = "off",
        incompatible: bool = False,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self.io = IO(
            inputs={"value": str if incompatible else list[int]},
            initial_values=self._initial_values,
            input_events=self.io.input_events,
            output_events=self.io.output_events,
            namespace=self.name,
            component=self,
            runtime_validation=mode,
        )
        self.received: list[_t.Any] = []

    async def step(self) -> None:
        """Record values without imposing additional checks."""
        self.received.append(self.value)


def _connector(cls: type[Connector] = AsyncioConnector) -> Connector:
    return cls(ConnectorSpec(source="source.value", target="sink.value"))


async def test_incompatible_connection_fails_before_setup() -> None:
    """Known type mismatches fail before initializing components or connections."""
    source, sink = Source(name="source"), DynamicSink(name="sink", incompatible=True)
    process = LocalProcess([source, sink], [_connector()])
    with pytest.raises(
        ValidationError, match=r"source.value \(list\[int\]\) -> sink.value \(str\)"
    ):
        await process.init()
    assert not process.is_initialised
    assert not process._state_is_connected
    assert not sink.io._input_channels


@pytest.mark.parametrize("mode", ["off", "shallow", "deep"])
async def test_runtime_channel_values(mode: RuntimeValidation) -> None:
    """Every channel payload is checked according to the selected policy."""
    source, sink = Source(name="source"), DynamicSink(name="sink", mode=mode)
    process = LocalProcess([source, sink], [_connector()])
    async with process:
        assert process.is_initialised
        await process.step()
        assert sink.received == [[1]]
        # A valid first value does not exempt later messages from checking.
        source._invalid = True
        if mode == "deep":
            with pytest.raises(ExceptionGroup) as exc:
                await process.step()
            assert exc.group_contains(ValidationError, match=r"sink.value \(input\)\[0\]")
            assert sink.status == Status.FAILED
            assert process.status == Status.FAILED
            assert sink.received == [[1]]
        else:
            await process.step()
            assert sink.received == [[1], ["wrong"]]
        # Type metadata can be stored by JSON-based state backends.
        assert msgspec.json.decode(sink.json())["io"]["input_types"] == {"value": "list[int]"}


async def test_initial_values_are_checked() -> None:
    """Initial input values reach the same validation boundary as channel data."""
    source = Source(name="source")
    sink = DynamicSink(name="sink", mode="deep", initial_values={"value": [["wrong"]]})
    process = LocalProcess([source, sink], [_connector()])
    async with process:
        with pytest.raises(ExceptionGroup) as exc:
            await process.step()
        assert exc.group_contains(ValidationError, match="expected int, got str")
        assert sink.received == []


class PayloadEvent(Event):
    """An event that supplies an input field."""

    type: _t.ClassVar[str] = "typed_payload"
    value: _t.Any


class EventSink(Component):
    """Consumer populated through an event handler rather than a field connector."""

    io = IO(inputs={"value": int}, input_events=[PayloadEvent], runtime_validation="deep")

    @PayloadEvent.handler(populates_fields=["value"])
    async def receive(self, event: PayloadEvent) -> None:
        """Assign the event payload to the input."""
        self.value = event.value

    async def step(self) -> None:
        """Consume a valid input."""


async def test_event_assigned_inputs_are_checked() -> None:
    """Event assignments cannot bypass input validation."""
    sink = EventSink(name="event_sink")
    sink.io.buf_events["input"].put([PayloadEvent(source="test", data={}, value="wrong")])
    with pytest.raises(ValidationError, match=r"event_sink.value \(input\).*expected int"):
        await sink.step()
    assert sink.status == Status.FAILED


async def test_output_validation_fails_before_send() -> None:
    """Producer-side checking marks failures and prevents invalid output transmission."""

    class CheckedSource(Source):
        io = IO(runtime_validation="deep", validate_outputs=True)

    source = CheckedSource(name="source", invalid=True)
    channel = _t.cast(AsyncioConnector, _connector())
    await source.io.connect([channel])
    try:
        with pytest.raises(ValidationError, match=r"source.value \(output\)\[0\]"):
            await source.step()
        assert source.status == Status.FAILED
        assert channel._send_channel._queue.empty()
    finally:
        await source.io.close()


@pytest.mark.parametrize("incompatible", [False, True])
async def test_ray_typed_ports(incompatible: bool, ray_ctx: None) -> None:
    """Ray preserves dynamically declared types, policy, and serialized state."""
    source = Source(name="source", invalid=True)
    sink = DynamicSink(name="sink", mode="deep", incompatible=incompatible)
    process: Process = RayProcess([source, sink], [_connector(RayConnector)])
    try:
        if incompatible:
            with pytest.raises(ValidationError, match="Incompatible port types"):
                await process.init()
        else:
            await process.init()
            # Ray task errors retain the original exception type inside the group.
            with pytest.raises(ExceptionGroup) as exc:
                await process.step()
            assert exc.group_contains(ValidationError, match=r"sink.value \(input\)\[0\]")
            assert sink.status == Status.FAILED
            assert process.status == Status.FAILED
    finally:
        await process.destroy()
