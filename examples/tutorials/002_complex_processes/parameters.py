"""An example using process parameters."""

# fmt: off
import asyncio

from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

from components import Random, Save, ScaleFromParameter, Sum


async def main() -> None:
    # --8<-- [start:main]
    connect = lambda in_, out_: AsyncioConnector(
        spec=ConnectorSpec(source=in_, target=out_)
    )
    process = LocalProcess(
        components=[
            Random(name="random", iters=5, low=0, high=10),
            ScaleFromParameter(name="scale_a"),
            ScaleFromParameter(name="scale_b", parameters={"scale": 2.0}),  # (2)!
            Sum(name="sum"),
            Save(name="save-input", path="input.txt"),
            Save(name="save-output", path="output.txt"),
        ],
        connectors=[
            connect("random.x", "save-input.value_to_save"),
            connect("random.x", "scale_a.a"),
            connect("random.x", "scale_b.a"),
            connect("scale_a.x", "sum.a"),
            connect("scale_b.x", "sum.b"),
            connect("sum.x", "save-output.value_to_save"),
        ],
        parameters={"scale": 0.5},  # (1)!
    )
    async with process:
        await process.run()
    # --8<-- [end:main]

if __name__ == "__main__":
    asyncio.run(main())
