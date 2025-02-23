"""Integration tests for different `Process` topologies."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.component import IOController as IO
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec
from tests.conftest import ComponentTestHelper
from tests.integration.test_process_with_components_run import A, B


class C(ComponentTestHelper):
    io = IO(inputs=["in_1", "in_2"], outputs=["out_1", "out_2"])

    async def step(self) -> None:
        self.out_1, self.out_2 = self.in_1, self.in_2  # type: ignore
        await super().step()


@pytest.mark.anyio
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


@pytest.mark.anyio
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
