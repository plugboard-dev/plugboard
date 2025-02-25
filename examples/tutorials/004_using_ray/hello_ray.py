"""Comparison of `LocalProcess` and `RayProcess`."""

# fmt: off
import asyncio
import time

import ray

from plugboard.connector import RayConnector, AsyncioConnector
from plugboard.library import FileWriter
from plugboard.process import LocalProcess, RayProcess
from plugboard.schemas import ConnectorSpec
from components import Iterator, Sleep, Timestamper


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
