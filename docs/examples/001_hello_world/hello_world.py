"""Simple hello world example."""

# --8<-- [start:components]
import asyncio
import typing as _t

import aiofiles

from plugboard import Component
from plugboard.connector import ConnectorSpec
from plugboard.io import IOController as IO
from plugboard.process import ProcessBuilder


class A(Component):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = range(self._iters)

    async def step(self) -> None:
        self.out_1 = next(self._seq)

class B(Component):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._path = path

    async def step(self) -> None:
        out = 2 * self.in_1
        async with aiofiles.open(self._path, "a") as f:
            f.write(f"{out}\n")
# --8<-- [end:components]

async def main() -> None:
    # --8<-- [start:main]
    process = ProcessBuilder(
        components=[
            A(name="a", iters=10), B(name="b", path="./b.txt")
        ],
        connector_specs=[
            ConnectorSpec(source="a.out_1", target="b.in_1")
        ]
    )

    await process.init()
    await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())