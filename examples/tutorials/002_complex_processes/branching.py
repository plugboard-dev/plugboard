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
    process = LocalProcess(
        components=[  # (1)!
            Random(name="random", iters=5, low=0, high=10),
            Offset(name="offset", offset=10),
            Scale(name="scale", scale=2),
            Sum(name="sum"),
            Save(name="save-input", path="input.txt"),
            Save(name="save-output", path="output.txt"),
        ],
        connectors=[  # (2)!
            AsyncioConnector(
                spec=ConnectorSpec(source="random.x", target="save-input.value_to_save")
            ),
            AsyncioConnector(spec=ConnectorSpec(source="random.x", target="offset.a")),
            AsyncioConnector(spec=ConnectorSpec(source="random.x", target="scale.a")),
            AsyncioConnector(spec=ConnectorSpec(source="offset.x", target="sum.a")),
            AsyncioConnector(spec=ConnectorSpec(source="scale.x", target="sum.b")),
            AsyncioConnector(
                spec=ConnectorSpec(source="sum.x", target="save-output.value_to_save")
            ),
        ],
    )
    async with process:  # (3)!
        await process.run()
# --8<-- [end:main]

if __name__ == "__main__":
    asyncio.run(main())
