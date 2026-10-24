"""Deterministic workloads using the production component run loop."""

from dataclasses import dataclass
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec, Status


class Source(Component):
    """Emit a finite integer sequence without application computation or I/O."""

    io = IO(outputs=["value"])

    def __init__(self, messages: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.messages = messages
        self.sent = 0

    async def step(self) -> None:
        """Emit the next integer, closing the stream when exhausted."""
        if self.sent == self.messages:
            await self.io.close()
        else:
            self.value = self.sent
            self.sent += 1


class Relay(Component):
    """Forward values while recording delivery counts and checksums."""

    io = IO(inputs=["value"], outputs=["result"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.received = 0
        self.checksum = 0

    async def step(self) -> None:
        """Forward one input through the normal component I/O wrapper."""
        self.result = self.value
        self.received += 1
        self.checksum += self.value


class Join(Relay):
    """Synchronize two inputs, forwarding the first after both arrive."""

    io = IO(inputs=["value", "other"], outputs=["result"])


@dataclass(frozen=True)
class Workload:
    """A graph shape and its scale, with stable benchmark identifiers."""

    topology: str
    size: int

    @property
    def id(self) -> str:
        """Return the topology and scale for pytest result names."""
        return f"{self.topology}-{self.size}"

    def build(self, messages: int) -> tuple[LocalProcess, list[tuple[Relay, int]]]:
        """Construct a fresh process and expected message counts per receiver."""
        components: list[Component] = []
        connectors: list[AsyncioConnector] = []
        expected: list[tuple[Relay, int]] = []

        def source(name: str) -> Source:
            component = Source(messages=messages, name=name)
            components.append(component)
            return component

        def relay(name: str, count: int = messages, *, join: bool = False) -> Relay:
            component = Join(name=name) if join else Relay(name=name)
            components.append(component)
            expected.append((component, count))
            return component

        def connect(sender: Component, receiver: Component, field: str = "value") -> None:
            output = "value" if isinstance(sender, Source) else "result"
            connectors.append(
                AsyncioConnector(
                    spec=ConnectorSpec(
                        source=f"{sender.name}.{output}", target=f"{receiver.name}.{field}"
                    )
                )
            )

        if self.topology == "chain":
            previous: Component = source("source")
            for index in range(self.size - 1):
                receiver = relay(f"relay_{index}")
                connect(previous, receiver)
                previous = receiver
        elif self.topology == "fan_out":
            producer = source("source")
            for index in range(self.size):
                connect(producer, relay(f"receiver_{index}"))
        elif self.topology == "fan_in":
            receiver = relay("receiver", messages * self.size)
            for index in range(self.size):
                connect(source(f"source_{index}"), receiver)
        elif self.topology == "diamond":
            producer = source("source")
            left, right = relay("left"), relay("right")
            receiver = relay("join", join=True)
            connect(producer, left)
            connect(producer, right)
            connect(left, receiver)
            connect(right, receiver, "other")
        elif self.topology == "feedback":
            producer = source("source")
            receiver = Join(name="join", initial_values={"other": [-1]})
            components.append(receiver)
            expected.append((receiver, messages))
            feedback = relay("feedback")
            connect(producer, receiver)
            connect(receiver, feedback)
            connect(feedback, receiver, "other")
        else:
            raise ValueError(f"Unknown topology: {self.topology}")

        return LocalProcess(components, connectors, name=self.id), expected


def verify(process: LocalProcess, expected: list[tuple[Relay, int]], messages: int) -> None:
    """Reject incomplete runs even if they appear faster."""
    assert process.status == Status.COMPLETED
    assert all(component.status == Status.COMPLETED for component in process.components.values())
    for component, count in expected:
        assert component.received == count
        assert component.checksum == count * (messages - 1) // 2
