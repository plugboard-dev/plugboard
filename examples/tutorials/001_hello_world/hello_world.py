"""Simple hello world example."""

# fmt: off
# --8<-- [start:components]
import asyncio
from contextlib import AsyncExitStack
import time
import typing as _t

from aiofile import async_open
import structlog

from plugboard.component import Component, IOController as IO
from plugboard.connector import AsyncioChannel, Connector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec


logger = structlog.get_logger()


class A(Component):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        self.logger.info("Step")
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
        self.logger.info("Step")
        out = 2 * self.in_1
        await self._f.write(f"{out}\n")

    async def destroy(self) -> None:
        await self._ctx.aclose()
# --8<-- [end:components]


async def main() -> None:
    # --8<-- [start:main]
    process = LocalProcess(
        components=[A(name="a", iters=5), B(name="b", path="b.txt")],
        connectors=[
            Connector(
                spec=ConnectorSpec(source="a.out_1", target="b.in_1"),
                channel=AsyncioChannel(),
            )
        ],
    )
    async with process:
        await process.run()
    # --8<-- [end:main]


if __name__ == "__main__":
    tstart = time.time()
    asyncio.run(main())
    print(f"Elapsed: {time.time() - tstart:.2f} s")
