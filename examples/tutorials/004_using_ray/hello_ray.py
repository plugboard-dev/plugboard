"""Comparison of `LocalProcess` and `RayProcess`."""

# fmt: off
import asyncio
import datetime
import time
import typing as _t

import ray

from plugboard.component import Component, IOController as IO
from plugboard.connector import RayConnector, AsyncioConnector
from plugboard.library import FileWriter
from plugboard.process import LocalProcess, RayProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec


# --8<-- [start:components]
class Iterator(Component):
    """Creates a sequence of numbers."""

    io = IO(outputs=["x"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()


class Sleep(Component):
    """Passes through input to output after a delay."""

    io = IO(inputs=["x"], outputs=["y"])

    def __init__(self, sleep_seconds: float, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._duration = sleep_seconds

    async def step(self) -> None:
        time.sleep(self._duration)  # (1)!
        self.y = self.x


class Timestamper(Component):
    """Emits the current time when all inputs are ready."""

    io = IO(inputs=["x", "y"], outputs=["timestamp"])

    async def step(self) -> None:
        self.timestamp = datetime.datetime.now().isoformat()
# --8<-- [end:components]


async def local_main() -> None:
    # --8<-- [start:local]
    process = LocalProcess(
        components=[
            Iterator(name="input", iters=20),
            Sleep(name="slow-sleep", sleep_seconds=0.5),
            Sleep(name="very-slow-sleep", sleep_seconds=1),
            Timestamper(name="timestamper"),
            FileWriter(name="save-results", path="ray.csv", field_names=["timestamp"]),
        ],
        connectors=[
            AsyncioConnector(spec=ConnectorSpec(source="input.x", target="slow-sleep.x")),
            AsyncioConnector(spec=ConnectorSpec(source="input.x", target="very-slow-sleep.x")),
            AsyncioConnector(spec=ConnectorSpec(source="slow-sleep.y", target="timestamper.x")),
            AsyncioConnector(
                spec=ConnectorSpec(source="very-slow-sleep.y", target="timestamper.y")
            ),
            AsyncioConnector(
                spec=ConnectorSpec(source="timestamper.timestamp", target="save-results.timestamp")
            ),
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:local]


async def ray_main() -> None:
    # --8<-- [start:ray]
    process = RayProcess(
        components=[
            Iterator(name="input", iters=20),
            Sleep(name="slow-sleep", sleep_seconds=0.5),
            Sleep(name="very-slow-sleep", sleep_seconds=1),
            Timestamper(name="timestamper"),
            FileWriter(name="save-results", path="ray.csv", field_names=["timestamp"]),
        ],
        connectors=[
            RayConnector(spec=ConnectorSpec(source="input.x", target="slow-sleep.x")),
            RayConnector(spec=ConnectorSpec(source="input.x", target="very-slow-sleep.x")),
            RayConnector(spec=ConnectorSpec(source="slow-sleep.y", target="timestamper.x")),
            RayConnector(spec=ConnectorSpec(source="very-slow-sleep.y", target="timestamper.y")),
            RayConnector(
                spec=ConnectorSpec(source="timestamper.timestamp", target="save-results.timestamp")
            ),
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:ray]


if __name__ == "__main__":
    ray.init()

    tstart = time.time()
    asyncio.run(local_main())
    print(f"Local process took {time.time() - tstart:.2f} seconds.")
    tstart = time.time()
    asyncio.run(ray_main())
    print(f"Ray process took {time.time() - tstart:.2f} seconds.")
