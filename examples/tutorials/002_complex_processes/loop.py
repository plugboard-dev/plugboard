"""A looping model example."""

# fmt: off
# --8<-- [start:main]
import asyncio

from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

from components import Random, Save, Scale, Sum


async def main() -> None:
    # --8<-- [start:main]
    connect = lambda in_, out_: AsyncioConnector(
        spec=ConnectorSpec(source=in_, target=out_)
    )
    process = LocalProcess(
        components=[
            Random(name="random", iters=5, low=0, high=10),
            Sum(name="sum"),
            Scale(name="scale", initial_values={"a": [0]}, scale=0.5),  # (1)!
            Save(name="save-output", path="cumulative-sum.txt"),
        ],
        connectors=[
            connect("random.x", "sum.a"),
            connect("sum.x", "scale.a"),
            connect("scale.x", "sum.b"),
            connect("sum.x", "save-output.value_to_save"),
        ],
    )
    async with process:
        await process.run()
# --8<-- [end:main]

if __name__ == "__main__":
    asyncio.run(main())
