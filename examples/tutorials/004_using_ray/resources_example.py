"""Example demonstrating resource requirements for components in RayProcess."""

# fmt: off
import asyncio
import typing as _t

import ray

from plugboard.component import Component, IOController as IO
from plugboard.connector import RayConnector
from plugboard.process import RayProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec, Resource


# --8<-- [start:definition]
class CPUIntensiveTask(Component):
    """Component that requires more CPU resources.

    Resource requirements are declared as a class attribute.
    """

    io = IO(inputs=["x"], outputs=["y"])
    resources = Resource(cpu=2.0)   # (1)!

    async def step(self) -> None:
        """Execute CPU-intensive computation."""
        # Simulate CPU-intensive work
        result = sum(i**2 for i in range(int(self.x * 10000)))
        self.y = result
# --8<-- [end:definition]


class GPUTask(Component):
    """Component that requires GPU resources.

    Resource requirements are declared as a class attribute.
    """

    io = IO(inputs=["data"], outputs=["result"])
    resources = Resource(cpu="500m", gpu=1)  # Declare resources at class level

    async def step(self) -> None:
        """Execute GPU computation."""
        # Simulate GPU computation
        self.result = self.data * 2


class DataProducer(Component):
    """Produces data for processing."""

    io = IO(outputs=["output"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        """Initialize DataProducer with iteration count."""
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        """Initialize the data sequence."""
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        """Produce the next data value."""
        try:
            self.output = next(self._seq)
        except StopIteration:
            await self.io.close()


async def main() -> None:
    """Run the process with resource-constrained components."""
    # --8<-- [start:resources]
    # Resources can be declared at the class level (see CPUIntensiveTask and GPUTask above)
    # or overridden when instantiating components
    process = RayProcess(
        components=[
            CPUIntensiveTask(name="cpu-task", resources=Resource(cpu=1.0)),  # (1)!
            GPUTask(name="gpu-task"),  # (2)!
            DataProducer(name="producer", iters=5),  # (3)!
        ],
        connectors=[
            RayConnector(spec=ConnectorSpec(source="producer.output", target="cpu-task.x")),
            RayConnector(spec=ConnectorSpec(source="cpu-task.y", target="gpu-task.data")),
        ],
    )
    # --8<-- [end:resources]

    async with process:
        await process.run()

    print("Process completed successfully!")


if __name__ == "__main__":
    if not ray.is_initialized():
        # Ray must be initialised with the necessary resources
        ray.init(num_cpus=5, num_gpus=1, resources={"custom_hardware": 10}, include_dashboard=True)
    asyncio.run(main())
