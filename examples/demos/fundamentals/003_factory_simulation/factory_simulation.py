"""Factory simulation demo.

Simulates a factory with 5 machines over 1 year (365 days). Each machine:
- Produces $10,000 of value per day when running.
- Has a probability of random breakdown that increases with days since last maintenance
  (modelled as a sigmoid function with different parameters per machine).
- Stops for 5 days when it breaks down.
- Has a proactive maintenance schedule: stops for 1 day at regular intervals.

The simulation optimises the maintenance interval for each machine to maximise total output.
"""

import math
import random
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict


class Iterator(Component):
    """Drives the simulation by emitting a sequence of day numbers."""

    io = IO(outputs=["day"])

    def __init__(self, num_days: int = 365, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._num_days = num_days

    async def init(self) -> None:
        self._seq = iter(range(self._num_days))

    async def step(self) -> None:
        try:
            self.day = next(self._seq)
        except StopIteration:
            await self.io.close()


class Machine(Component):
    """Simulates a single factory machine.

    The machine can be in one of three states: running, broken, or under maintenance.
    When running, it produces a fixed daily output. Breakdown probability is modelled
    as a sigmoid function of days since last maintenance, with configurable steepness
    and midpoint parameters. Proactive maintenance occurs at regular intervals.

    Args:
        maintenance_interval: Number of days between proactive maintenance stops.
        breakdown_days: Number of days the machine is offline after a breakdown.
        maintenance_days: Number of days the machine is offline for proactive maintenance.
        daily_output: Value produced per day when running.
        sigmoid_steepness: Controls how quickly breakdown probability rises.
        sigmoid_midpoint: Days since maintenance at which breakdown probability is 50%.
        seed: Random seed for reproducible results.
    """

    io = IO(inputs=["day"], outputs=["daily_value"])

    def __init__(
        self,
        maintenance_interval: int = 30,
        breakdown_days: int = 5,
        maintenance_days: int = 1,
        daily_output: float = 10_000.0,
        sigmoid_steepness: float = 0.15,
        sigmoid_midpoint: float = 40.0,
        seed: int = 42,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._maintenance_interval = maintenance_interval
        self._breakdown_days = breakdown_days
        self._maintenance_days = maintenance_days
        self._daily_output = daily_output
        self._sigmoid_steepness = sigmoid_steepness
        self._sigmoid_midpoint = sigmoid_midpoint
        self._seed = seed

    async def init(self) -> None:
        self._rng = random.Random(self._seed)
        self._days_since_maintenance = 0
        self._downtime_remaining = 0

    def _breakdown_probability(self) -> float:
        """Sigmoid function: probability near 0 soon after maintenance, rising to ~1."""
        return 1.0 / (
            1.0
            + math.exp(
                -self._sigmoid_steepness * (self._days_since_maintenance - self._sigmoid_midpoint)
            )
        )

    async def step(self) -> None:
        # If machine is down (breakdown or maintenance), count down
        if self._downtime_remaining > 0:
            self._downtime_remaining -= 1
            self.daily_value = 0.0
            if self._downtime_remaining == 0:
                self._days_since_maintenance = 0
            return

        # Check for proactive maintenance
        if (
            self._maintenance_interval > 0
            and self._days_since_maintenance > 0
            and self._days_since_maintenance % self._maintenance_interval == 0
        ):
            self._downtime_remaining = self._maintenance_days
            self.daily_value = 0.0
            return

        # Check for random breakdown
        if self._rng.random() < self._breakdown_probability():
            self._downtime_remaining = self._breakdown_days
            self.daily_value = 0.0
            return

        # Machine is running normally
        self.daily_value = self._daily_output
        self._days_since_maintenance += 1


class Factory(Component):
    """Aggregates daily output from all 5 machines and tracks total value."""

    io = IO(
        inputs=["value_1", "value_2", "value_3", "value_4", "value_5"],
        outputs=["total_value"],
    )

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)

    async def init(self) -> None:
        self._total = 0.0

    async def step(self) -> None:
        daily = self.value_1 + self.value_2 + self.value_3 + self.value_4 + self.value_5
        self._total += daily
        self.total_value = self._total


# Machine configurations: each has different sigmoid parameters
MACHINE_CONFIGS: list[dict[str, _t.Any]] = [
    {"sigmoid_steepness": 0.10, "sigmoid_midpoint": 50.0, "seed": 101},  # Reliable
    {"sigmoid_steepness": 0.12, "sigmoid_midpoint": 45.0, "seed": 202},  # Average
    {"sigmoid_steepness": 0.15, "sigmoid_midpoint": 40.0, "seed": 303},  # Average
    {"sigmoid_steepness": 0.18, "sigmoid_midpoint": 35.0, "seed": 404},  # Fragile
    {"sigmoid_steepness": 0.20, "sigmoid_midpoint": 30.0, "seed": 505},  # Very fragile
]
