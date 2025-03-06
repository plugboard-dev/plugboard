"""Reusable components."""

# fmt: off
# --8<-- [start:components]
import random
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class Random(Component):
    io = IO(outputs=["x"])

    def __init__(
            self,
            iters: int,  # (1)!
            low: float = 0,
            high: float = 10,
            **kwargs: _t.Unpack[ComponentArgsDict]
        ) -> None:
        super().__init__(**kwargs)
        self._iters = 0
        self._low = low
        self._high = high
        self._max_iters = iters

    async def step(self) -> None:
        if self._iters < self._max_iters:
            self.x = random.uniform(self._low, self._high)
            self._iters += 1
            return
        await self.io.close()

class Offset(Component):
    """Implements `x = a + offset`."""
    io = IO(inputs=["a"], outputs=["x"]) # (2)!

    def __init__(self, offset: float = 0, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._offset = offset

    async def step(self) -> None:
        self.x = self.a + self._offset

class Scale(Component):
    """Implements `x = a * scale`."""
    io = IO(inputs=["a"], outputs=["x"])

    def __init__(self, scale: float = 1, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._scale = scale

    async def step(self) -> None:
        self.x = self.a * self._scale

class Sum(Component):
    """Implements `x = a + b`."""
    io = IO(inputs=["a", "b"], outputs=["x"]) # (3)!

    async def step(self) -> None:
        self.x = self.a + self.b

class Save(Component):
    io = IO(inputs=["value_to_save"])

    def __init__(self, path: str, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._path = path

    async def init(self) -> None:
        self._f = open(self._path, "w")

    async def step(self) -> None:
        self._f.write(f"{self.value_to_save}\n")

    async def destroy(self) -> None:
        self._f.close()
# --8<-- [end:components]
