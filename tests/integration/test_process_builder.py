"""Integration tests for `ProcessBuilder`."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.process import ProcessBuilder
from plugboard.schemas import (
    ChannelBuilderArgsSpec,
    ChannelBuilderSpec,
    ComponentSpec,
    ConnectorSpec,
    ProcessArgsSpec,
    ProcessSpec,
)


@pytest.fixture
def process_spec() -> ProcessSpec:
    """Returns a `ProcessSpec` for testing."""
    return ProcessSpec(
        args=ProcessArgsSpec(
            components=[
                ComponentSpec(
                    type="tests.integration.test_process_with_components_run.A",
                    args={"name": "A", "iters": 10},
                ),
                ComponentSpec(
                    type="tests.integration.test_process_with_components_run.B",
                    args={"name": "B", "factor": 45},
                ),
                ComponentSpec(
                    type="tests.integration.test_process_with_components_run.C",
                    args={"name": "C", "path": "/tmp/test.txt"},
                ),
            ],
            connectors=[
                ConnectorSpec(
                    source="A.out_1",
                    target="B.in_1",
                ),
                ConnectorSpec(
                    source="B.out_1",
                    target="C.in_1",
                ),
            ],
            parameters={},
        ),
        channel_builder=ChannelBuilderSpec(
            type="plugboard.connector.AsyncioChannelBuilder",
            args=ChannelBuilderArgsSpec(),
        ),
    )


@pytest.mark.anyio
async def test_process_builder_build(process_spec: ProcessSpec) -> None:
    """Tests building a process."""
    process = ProcessBuilder.build(process_spec)
    # Must build a process with the correct components and connectors
    assert len(process.components) == 3
    assert len(process.connectors) == 2
