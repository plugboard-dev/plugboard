"""Defines components used in the production line example."""

import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict


class Input(Component):
    """Provides a fixed number of input items per step."""

    io = IO(outputs=["items"])

    def __init__(
        self,
        items_per_step: int = 10,
        total_steps: int = 1000,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._items_per_step = items_per_step
        self._total_steps = total_steps

    async def step(self) -> None:
        self.items = self._items_per_step
        if self._total_steps > 0:
            self._total_steps -= 1
        else:
            self.items = 0
            await self.io.close()


class InputStockpile(Component):
    """Tracks input stockpile, decrements based on machine operations, and calculates storage costs."""

    io = IO(
        inputs=["incoming_items", "machine1_running", "machine2_running"],
        outputs=["size", "storage_cost"],
    )

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._size = 0

    async def step(self) -> None:
        # Add incoming items
        self._size += self.incoming_items

        # Remove items processed by machines
        if self.machine1_running:
            self._size = max(0, self._size - 5)  # Machine 1 processes 5 items
        if self.machine2_running:
            self._size = max(0, self._size - 8)  # Machine 2 processes 8 items

        # Calculate storage cost: $10 per item above 50
        storage_cost = max(0, self._size - 50) * 10

        self.size = self._size
        self.storage_cost = storage_cost


class Controller(Component):
    """Controls machine operation based on stockpile size."""

    io = IO(inputs=["stockpile_size"], outputs=["should_run"])

    def __init__(self, threshold: int = 30, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._threshold = threshold

    async def step(self) -> None:
        self.should_run = self.stockpile_size >= self._threshold


class MachineCost(Component):
    """Calculates machine running costs."""

    io = IO(inputs=["is_running"], outputs=["cost"])

    def __init__(
        self, cost_per_step: float = 100.0, **kwargs: _t.Unpack[ComponentArgsDict]
    ) -> None:
        super().__init__(**kwargs)
        self._cost_per_step = cost_per_step

    async def step(self) -> None:
        self.cost = self._cost_per_step if self.is_running else 0.0


class OutputStock(Component):
    """Tracks total items processed by both machines."""

    io = IO(inputs=["machine1_running", "machine2_running"], outputs=["total_output"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._total = 0

    async def step(self) -> None:
        if self.machine1_running:
            self._total += 5
        if self.machine2_running:
            self._total += 8
        self.total_output = self._total


class TotalCost(Component):
    """Keeps running total of all costs."""

    io = IO(inputs=["storage_cost", "machine1_cost", "machine2_cost"], outputs=["total_cost"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._total = 0.0

    async def step(self) -> None:
        step_cost = self.storage_cost + self.machine1_cost + self.machine2_cost
        self._total += step_cost
        self.total_cost = self._total


class CostPerUnit(Component):
    """Calculates cost per unit produced."""

    io = IO(inputs=["total_cost", "total_output"], outputs=["cost_per_unit"])

    async def step(self) -> None:
        if self.total_output > 0:
            self.cost_per_unit = self.total_cost / self.total_output
        else:
            self.cost_per_unit = 0.0
