"""Example demonstrating resource requirements for components in RayProcess."""

import asyncio
import typing as _t

import ray

from plugboard.component import Component, IOController as IO
from plugboard.connector import RayConnector
from plugboard.process import RayProcess
from plugboard.schemas import ComponentArgsDict, ConnectorSpec, Resource


class CPUIntensiveTask(Component):
    """Component that requires more CPU resources."""

    io = IO(inputs=["x"], outputs=["y"])

    async def step(self) -> None:
        # Simulate CPU-intensive work
        result = sum(i**2 for i in range(int(self.x * 10000)))
        self.y = result


class GPUTask(Component):
    """Component that requires GPU resources."""

    io = IO(inputs=["data"], outputs=["result"])

    async def step(self) -> None:
        # Simulate GPU computation
        self.result = self.data * 2


class DataProducer(Component):
    """Produces data for processing."""

    io = IO(outputs=["output"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.output = next(self._seq)
        except StopIteration:
            await self.io.close()


async def main() -> None:
    """Run the process with resource-constrained components."""
    # Define resource requirements for components
    # --8<-- [start:resources]
    cpu_resources = Resource(cpu=2.0)  # Requires 2 CPUs
    gpu_resources = Resource(cpu="500m", gpu=1)  # Requires 0.5 CPU and 1 GPU

    process = RayProcess(
        components=[
            DataProducer(name="producer", iters=5, resources=cpu_resources),
            CPUIntensiveTask(name="cpu-task", resources=cpu_resources),
            GPUTask(name="gpu-task", resources=gpu_resources),
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
