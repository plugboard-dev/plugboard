"""A looping model example."""

# fmt: off
# --8<-- [start:main]
import asyncio

from plugboard.connector import AsyncioChannel, Connector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

from components import Random, Save, Scale, Sum


async def main() -> None:
    # --8<-- [start:main]
    process = LocalProcess(
        components=[
            Random(name="random", iters=5, low=0, high=10),
            Sum(name="sum"),
            Scale(name="scale", initial_values={"a": [0]}, scale=0.5),  # (1)!
            Save(name="save-output", path="cumulative-sum.txt"),
        ],
        connectors=[
            Connector(
                spec=ConnectorSpec(source="random.x", target="sum.a"),
                channel=AsyncioChannel(),
            ),
            Connector(
                spec=ConnectorSpec(source="sum.x", target="scale.a"),
                channel=AsyncioChannel(),
            ),
            Connector(
                spec=ConnectorSpec(source="scale.x", target="sum.b"),
                channel=AsyncioChannel(),
            ),
            Connector(
                spec=ConnectorSpec(source="sum.x", target="save-output.value_to_save"),
                channel=AsyncioChannel(),
            ),
        ],
    )
    async with process:
        await process.run()
# --8<-- [end:main]

if __name__ == "__main__":
    asyncio.run(main())
