"""Event-based model example."""

# fmt: off
import asyncio
import random
import typing as _t

from pydantic import BaseModel

from plugboard.component import Component, IOController
from plugboard.connector import AsyncioConnector, ConnectorBuilder
from plugboard.events import Event, EventConnectorBuilder, StopEvent
from plugboard.library import FileWriter
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec, ComponentArgsDict


# --8<-- [start:events]
class ExtremeValue(BaseModel):
    """Data for event_A."""

    value: float
    extreme_type: _t.Literal["high", "low"]


class HighEvent(Event):
    """High value event type."""

    type: _t.ClassVar[str] = "high_event"
    data: ExtremeValue


class LowEvent(Event):
    """Low value event type."""

    type: _t.ClassVar[str] = "low_event"
    data: ExtremeValue
# --8<-- [end:events]


# --8<-- [start:source-component]
class Random(Component):
    """Generates random numbers."""

    io = IOController(outputs=["value"])

    def __init__(self, iters: int = 50, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.max_iters = iters
        self.completed_iters = 0

    async def step(self) -> None:
        self.completed_iters += 1
        self.value = random.random()
        if self.completed_iters >= self.max_iters:
            await self.io.close()
# --8<-- [end:source-component]


# --8<-- [start:event-publisher]
class FindHighLowValues(Component):
    """Publishes an event on high or low values."""

    io = IOController(inputs=["value"], output_events=[LowEvent, HighEvent])  # (1)!

    def __init__(
        self,
        low_limit: float = 0.2,
        high_limit: float = 0.8,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self.low_limit = low_limit
        self.high_limit = high_limit

    async def step(self) -> None:
        if self.value >= self.high_limit:
            self.io.queue_event(  # (2)!
                HighEvent(
                    source=self.name, data=ExtremeValue(value=self.value, extreme_type="high")
                )
            )
        if self.value <= self.low_limit:
            self.io.queue_event(
                LowEvent(source=self.name, data=ExtremeValue(value=self.value, extreme_type="low"))
            )
# --8<-- [end:event-publisher]


# --8<-- [start:event-consumers]
class CollectHigh(Component):
    """Collects values from high events."""

    io = IOController(input_events=[HighEvent], outputs=["value"])  # (1)!

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.latest_event: _t.Optional[ExtremeValue] = None

    async def step(self) -> None:
        self.value = self.latest_event.value if self.latest_event else None

    @HighEvent.handler  # (2)!
    async def handle_event(self, event: HighEvent) -> None:
        self.latest_event = event.data


class CollectLow(Component):
    """Collects values from low events."""

    io = IOController(input_events=[LowEvent], outputs=["value"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.latest_event: _t.Optional[ExtremeValue] = None

    async def step(self) -> None:
        self.value = self.latest_event.value if self.latest_event else None

    @LowEvent.handler  # (3)!
    async def handle_event(self, event: LowEvent) -> None:
        self.latest_event = event.data
# --8<-- [end:event-consumers]


async def main() -> None:
    # --8<-- [start:main]
    components = [
        Random(name="random-generator"),
        FindHighLowValues(name="find-high-low", low_limit=0.2, high_limit=0.8),
        CollectHigh(name="collect-high"),
        CollectLow(name="collect-low"),
        FileWriter(name="save-high", path="high.csv", field_names=["value"]),
        FileWriter(name="save-low", path="low.csv", field_names=["value"]),
    ]
    connect = lambda in_, out_: AsyncioConnector(spec=ConnectorSpec(source=in_, target=out_))
    connectors = [  # (1)!
        connect("random-generator.value", "find-high-low.value"),
        connect("collect-high.value", "save-high.value"),
        connect("collect-low.value", "save-low.value"),
    ]
    connector_builder = ConnectorBuilder(connector_cls=AsyncioConnector)  # (2)!
    event_connector_builder = EventConnectorBuilder(connector_builder=connector_builder)
    event_connectors = list(event_connector_builder.build(components).values())

    process = LocalProcess(
        components=components,
        connectors=connectors + event_connectors,
    )

    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())
