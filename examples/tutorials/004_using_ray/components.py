"""Components for Ray tutorial."""

# fmt: off
# --8<-- [start:components]
import datetime
import typing as _t
import time

from plugboard.component import Component, IOController as IO


class Iterator(Component):
    """Creates a sequence of numbers."""

    io = IO(outputs=["x"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()


class Sleep(Component):
    """Passes through input to output after a delay."""

    io = IO(inputs=["x"], outputs=["y"])

    def __init__(self, sleep_seconds: float, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._duration = sleep_seconds

    async def step(self) -> None:
        time.sleep(self._duration)  # (1)!
        self.y = self.x


class Timestamper(Component):
    """Emits the current time when all inputs are ready."""

    io = IO(inputs=["x", "y"], outputs=["timestamp"])

    async def step(self) -> None:
        self.timestamp = datetime.datetime.now().isoformat()
# --8<-- [end:components]
