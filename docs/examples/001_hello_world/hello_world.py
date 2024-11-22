"""Simple hello world example."""

# fmt: off
# --8<-- [start:components]
import asyncio
from contextlib import AsyncExitStack
import typing as _t

from aiofile import async_open

from plugboard.component import Component
from plugboard.component import IOController as IO
from plugboard.connector import AsyncioChannel, Connector
from plugboard.process import Process
from plugboard.schemas import ConnectorSpec


class A(Component):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()


class B(Component):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._path = path
        self._ctx = AsyncExitStack()

    async def init(self) -> None:
        self._f = await self._ctx.enter_async_context(
            async_open(self._path, "w")
        )

    async def step(self) -> None:
        out = 2 * self.in_1
        await self._f.write(f"{out}\n")

    async def destroy(self) -> None:
        await self._ctx.aclose()
# --8<-- [end:components]


async def main() -> None:
    # --8<-- [start:main]
    process = Process(
        components=[A(name="comp_a", iters=10), B(name="comp_b", path="comp_b.txt")],
        connectors=[
            Connector(
                spec=ConnectorSpec(source="comp_a.out_1", target="comp_b.in_1"),
                channel=AsyncioChannel(),
            )
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    asyncio.run(main())
