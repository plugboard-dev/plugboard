"""A branching model example."""

# fmt: off
# --8<-- [start:main]
import asyncio

from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

from components import Offset, Random, Save, Scale, Sum


async def main() -> None:
    # --8<-- [start:main]
    connect = lambda in_, out_: AsyncioConnector(  # (1)!
        spec=ConnectorSpec(source=in_, target=out_)
    )
    process = LocalProcess(
        components=[  # (2)!
            Random(name="random", iters=5, low=0, high=10),
            Offset(name="offset", offset=10),
            Scale(name="scale", scale=2),
            Sum(name="sum"),
            Save(name="save-input", path="input.txt"),
            Save(name="save-output", path="output.txt"),
        ],
        connectors=[  # (3)!
            connect("random.x", "save-input.value_to_save"),
            connect("random.x", "offset.a"),
            connect("random.x", "scale.a"),
            connect("offset.x", "sum.a"),
            connect("scale.x", "sum.b"),
            connect("sum.x", "save-output.value_to_save"),
        ],
    )
    async with process:  # (3)!
        await process.run()
# --8<-- [end:main]

if __name__ == "__main__":
    asyncio.run(main())
