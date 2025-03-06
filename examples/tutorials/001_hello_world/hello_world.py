"""Simple hello world example."""

# fmt: off
# --8<-- [start:components]
import asyncio
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec

class A(Component):
    io = IO(outputs=["out_1"]) # (1)!

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters)) # (2)!

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq) # (3)!
        except StopIteration:
            await self.io.close() # (5)!

class B(Component):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._path = path

    async def init(self) -> None:
        self._f = open(self._path, "w")

    async def step(self) -> None:
        out = 2 * self.in_1
        self._f.write(f"{out}\n")

    async def destroy(self) -> None:
        self._f.close() # (4)!
# --8<-- [end:components]


async def main() -> None:
    # --8<-- [start:main]
    process = LocalProcess(
        components=[A(name="a", iters=5), B(name="b", path="b.txt")],
        connectors=[
            AsyncioConnector(
                spec=ConnectorSpec(source="a.out_1", target="b.in_1"),
            )
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())
