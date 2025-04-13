"""Integration tests for different `Process` topologies."""
# ruff: noqa: D101,D102,D103

import asyncio
import typing as _t

import pytest

from plugboard.component import IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.diagram import markdown_diagram
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from tests.conftest import ComponentTestHelper
from tests.integration.test_process_with_components_run import A, B


class C(ComponentTestHelper):
    io = IO(inputs=["in_1", "in_2"], outputs=["out_1", "out_2"])

    async def step(self) -> None:
        self.out_1, self.out_2 = self.in_1, self.in_2  # type: ignore
        await super().step()


class D(ComponentTestHelper):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, factor: float = 1.0, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters
        self._factor = factor

    async def init(self) -> None:
        await super().init()
        self._seq = iter(range(1, self._iters + 1))

    async def step(self) -> None:
        try:
            value = next(self._seq)
            self.out_1 = int(self._factor * value)
            await asyncio.sleep(0.1)
        except StopIteration:
            await self.io.close()
        else:
            await super().step()


@pytest.mark.asyncio
async def test_circular_process_topology() -> None:
    """Tests a circular `Process` topology."""
    comp_a = A(name="comp_a", iters=10)
    comp_b = B(name="comp_b", factor=2)
    comp_c = C(name="comp_c", initial_values={"in_2": [-1]})
    components = [comp_a, comp_b, comp_c]

    conn_ac = AsyncioConnector(spec=ConnectorSpec(source="comp_a.out_1", target="comp_c.in_1"))
    conn_cb = AsyncioConnector(spec=ConnectorSpec(source="comp_c.out_1", target="comp_b.in_1"))
    # Circular connection
    conn_bc = AsyncioConnector(spec=ConnectorSpec(source="comp_b.out_1", target="comp_c.in_2"))
    connectors = [conn_ac, conn_cb, conn_bc]

    process = LocalProcess(components, connectors)

    # Process should run without error
    async with process:
        await process.run()

    # Check the final inputs/outputs
    assert comp_c.in_1 == 9
    assert comp_c.in_2 == 8 * 2
    assert comp_c.out_1 == 9
    assert comp_c.out_2 == 8 * 2

    assert all(comp.is_finished for comp in components)

    # Create a markdown diagram of the process without error
    _ = markdown_diagram(process)


@pytest.mark.asyncio
async def test_branching_process_topology() -> None:
    """Tests a branching `Process` topology."""
    comp_a = A(name="comp_a", iters=10)
    comp_b1 = B(name="comp_b1", factor=1)
    comp_b2 = B(name="comp_b2", factor=2)
    comp_c = C(name="comp_c")
    components = [comp_a, comp_b1, comp_b2, comp_c]

    conn_ab1 = AsyncioConnector(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b1.in_1"))
    conn_ab2 = AsyncioConnector(spec=ConnectorSpec(source="comp_a.out_1", target="comp_b2.in_1"))
    conn_b1c = AsyncioConnector(spec=ConnectorSpec(source="comp_b1.out_1", target="comp_c.in_1"))
    conn_b2c = AsyncioConnector(spec=ConnectorSpec(source="comp_b2.out_1", target="comp_c.in_2"))
    connectors = [conn_ab1, conn_ab2, conn_b1c, conn_b2c]

    process = LocalProcess(components, connectors)

    # Process should run without error
    async with process:
        await process.run()

    # Check the final outputs
    assert comp_c.out_1 == 9
    assert comp_c.out_2 == 9 * 2

    assert all(comp.is_finished for comp in components)

    # Create a markdown diagram of the process without error
    _ = markdown_diagram(process)


@pytest.mark.asyncio
async def test_multiple_inputs_to_one_field_process_topology() -> None:
    """Tests a `Process` topology with multiple inputs to a single field."""
    comp_d1 = D(name="comp_d1", iters=3, factor=1)
    comp_d2 = D(name="comp_d2", iters=3, factor=4)
    comp_d3 = D(name="comp_d3", iters=6, factor=5)
    comp_c = C(name="comp_c")
    components = [comp_d1, comp_d2, comp_d3, comp_c]

    # Connect both D1.out_1 and D2.out_1 to C.in_1
    conn_d1c = AsyncioConnector(spec=ConnectorSpec(source="comp_d1.out_1", target="comp_c.in_1"))
    conn_d2c = AsyncioConnector(spec=ConnectorSpec(source="comp_d2.out_1", target="comp_c.in_1"))
    conn_d3c = AsyncioConnector(spec=ConnectorSpec(source="comp_d3.out_1", target="comp_c.in_2"))
    connectors = [conn_d1c, conn_d2c, conn_d3c]

    process = LocalProcess(components, connectors)

    # Process should run without error
    async with process:
        await process.run()

    # We expect C.in_1 to have the last value received from either D1 or D2
    assert comp_c.in_1 in (3, 12)  # Either D1's final output (3) or D2's final output (3*4=12)
    assert comp_c.in_2 == 30  # Should be D3's final output (6*5=30)

    # Both outputs should match the inputs
    assert comp_c.out_1 == comp_c.in_1
    assert comp_c.out_2 == comp_c.in_2

    assert all(comp.is_finished for comp in components)

    # Create a markdown diagram of the process without error
    _ = markdown_diagram(process)
