"""Optimisation demonstration."""

# fmt: off
import typing as _t
from optuna import Trial
from plugboard.component import Component, IOController as IO
from plugboard.process import ProcessBuilder
from plugboard.schemas import ComponentArgsDict, ProcessSpec, ProcessArgsSpec, ObjectiveSpec
from plugboard.schemas.tune import FloatParameterSpec
from plugboard.tune import Tuner
import math


# --8<-- [start:components]
class Iterator(Component):
    """Creates a sequence of x values."""

    io = IO(outputs=["x"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.x = next(self._seq)
        except StopIteration:
            await self.io.close()


class Trajectory(Component):
    """Computes the height of a projectile."""

    io = IO(inputs=["x"], outputs=["y"])

    def __init__(
        self, angle: float = 30, velocity: float = 20, **kwargs: _t.Unpack[ComponentArgsDict]
    ) -> None:
        super().__init__(**kwargs)
        self._angle_radians = math.radians(angle)
        self._v0 = velocity

    async def step(self) -> None:
        self._logger.info("Calculating trajectory", x=self.x)
        self.y = self.x * math.tan(self._angle_radians) - (9.81 * self.x**2) / (
            2 * self._v0**2 * math.cos(self._angle_radians) ** 2
        )


class MaxHeight(Component):
    """Record the maximum height achieved."""

    io = IO(inputs=["y"], outputs=["max_y"])

    def __init__(self, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self.max_y: float = 0

    async def step(self) -> None:
        self.max_y = max(self.y, self.max_y)
# --8<-- [end:components]


# --8<-- [start:custom_search_space]
def custom_space(trial: Trial) -> dict[str, _t.Any] | None:
    """Defines a custom search space for Optuna."""
    angle = trial.suggest_int("trajectory.angle", 0, 90)
    # Make velocity depend on angle
    trial.suggest_int("trajectory.velocity", angle, 100)
# --8<-- [end:custom_search_space]


if __name__ == "__main__":
    # --8<-- [start:define_process]
    process_spec = ProcessSpec(
        args=ProcessArgsSpec(
            components=[
                {"type": "hello_tuner.Iterator", "args": {"name": "horizontal", "iters": 100}},
                {
                    "type": "hello_tuner.Trajectory",
                    "args": {"name": "trajectory", "angle": 30, "velocity": 20},
                },
                {"type": "hello_tuner.MaxHeight", "args": {"name": "max-height"}},
            ],
            connectors=[
                {"source": "horizontal.x", "target": "trajectory.x"},
                {"source": "trajectory.y", "target": "max-height.y"},
            ],
        ),
        type="plugboard.process.LocalProcess",
    )
    # Check that the process spec can be built
    _ = ProcessBuilder.build(spec=process_spec)
    # --8<-- [end:define_process]
    # --8<-- [start:run_tuner]
    tuner = Tuner(
        objective=ObjectiveSpec(  # (1)!
            object_type="component",
            object_name="max-height",
            field_type="field",
            field_name="max_y",
        ),
        parameters=[
            FloatParameterSpec(  # (2)!
                object_type="component",
                object_name="trajectory",
                field_type="arg",
                field_name="angle",
                lower=0,
                upper=90,
            ),
            FloatParameterSpec(
                object_type="component",
                object_name="trajectory",
                field_type="arg",
                field_name="velocity",
                lower=0,
                upper=100,
            ),
        ],
        num_samples=40,  # (3)!
        max_concurrent=4,  # (4)!
        mode="max",  # (5)!
    )
    result = tuner.run(spec=process_spec)
    print(
        f"Best parameters: angle={result.config['trajectory.angle']}, velocity={result.config['trajectory.velocity']}"
    )
    print(f"Best max height: {result.metrics['max-height.max_y']}")
    # --8<-- [end:run_tuner]
