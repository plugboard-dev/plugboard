"""Integration tests for `ProcessBuilder`."""
# ruff: noqa: D101,D102,D103

from tempfile import TemporaryDirectory
import typing as _t

import msgspec
import pytest

from plugboard.component import IOController as IO
from plugboard.events import Event
from plugboard.process import LocalProcess, ProcessBuilder
from plugboard.schemas import (
    ComponentSpec,
    ConnectorBuilderArgsSpec,
    ConnectorBuilderSpec,
    ConnectorSpec,
    ProcessArgsSpec,
    ProcessSpec,
    StateBackendSpec,
)
from plugboard.utils import EntityIdGen
from tests.conftest import ComponentTestHelper


class DummyEvent1(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "DummyEvent1"


class DummyEvent2(Event):
    """An event type for testing."""

    type: _t.ClassVar[str] = "DummyEvent2"


class D(ComponentTestHelper):
    io = IO(input_events=[DummyEvent1, DummyEvent2])

    async def step(self) -> None:
        pass

    @DummyEvent1.handler
    async def dummy_event_1_handler(self, event: DummyEvent1) -> None:
        pass

    @DummyEvent2.handler
    async def dummy_event_2_handler(self, event: DummyEvent2) -> None:
        pass


class E(ComponentTestHelper):
    io = IO(output_events=[DummyEvent1, DummyEvent2])

    async def step(self) -> None:
        pass


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
                    args={"name": "C", "path": "/tmp/test.txt"},  # noqa: S108
                ),
                ComponentSpec(
                    type="tests.integration.test_process_builder.D",
                    args={"name": "D"},
                ),
                ComponentSpec(
                    type="tests.integration.test_process_builder.E",
                    args={"name": "E"},
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
            state=StateBackendSpec(
                type="plugboard.state.DictStateBackend",
                args={"job_id": None, "metadata": {"hello": "world"}},
            ),
        ),
        connector_builder=ConnectorBuilderSpec(
            type="plugboard.connector.AsyncioConnector",
            args=ConnectorBuilderArgsSpec(parameters={}),
        ),
    )


@pytest.mark.asyncio
async def test_process_builder_build(process_spec: ProcessSpec) -> None:
    """Tests building a process."""
    process = ProcessBuilder.build(process_spec)
    # Must build a process with the correct type
    process.__class__.__name__ == process_spec.args.state.type.split(".")[-1]
    # Must build a process with the correct components and connectors
    assert len(process.components) == 5
    # Number of connectors must be sum of: fields in config; user events; and system events
    assert len(process.connectors) == 2 + 2 + 1
    # Must build a process with the correct component names
    assert process.components.keys() == {"A", "B", "C", "D", "E"}
    # Must build connectors with the correct channel types
    assert all(
        conn.__class__.__name__ == "AsyncioConnector" for conn in process.connectors.values()
    )
    # Must build a process with the correct state backend
    async with process:
        input_job_id = process_spec.args.state.args.model_dump().get("job_id")
        if input_job_id is not None:
            assert process.state.job_id == input_job_id
        assert EntityIdGen.is_job_id(process.state.job_id)
        assert process.state.metadata == {"hello": "world"}
    # Must be possible to export process to YAML
    with TemporaryDirectory() as tmpdir:
        process.dump(f"{tmpdir}/process.yaml")
        with open(f"{tmpdir}/process.yaml", "rb") as f:
            loaded = msgspec.yaml.decode(f.read())
    reconstructed_spec = ProcessSpec.model_validate(loaded["plugboard"]["process"])
    # Component names and types must match after export and re-import
    assert {(comp.args.name, comp.type) for comp in process_spec.args.components} == {
        (comp.args.name, comp.type) for comp in reconstructed_spec.args.components
    }
    # Unsupported extensions must raise an error
    with TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError):
            process.dump(f"{tmpdir}/process.txt")


@pytest.mark.asyncio
async def test_process_dump_with_default_state_and_parameters() -> None:
    """Test that process.dump works when state and parameters are not explicitly provided."""
    from plugboard.connector import AsyncioConnector
    from plugboard.schemas import ConnectorSpec

    class SimpleA(ComponentTestHelper):
        io = IO(outputs=["out_1"])

        async def step(self) -> None:
            pass

    class SimpleB(ComponentTestHelper):
        io = IO(inputs=["in_1"])

        async def step(self) -> None:
            pass

    process = LocalProcess(
        components=[SimpleA(name="A"), SimpleB(name="B")],
        connectors=[AsyncioConnector(spec=ConnectorSpec(source="A.out_1", target="B.in_1"))],
    )
    with TemporaryDirectory() as tmpdir:
        # Must not raise a validation error when state and parameters are not set
        process.dump(f"{tmpdir}/process.yaml")
        with open(f"{tmpdir}/process.yaml", "rb") as f:
            loaded = msgspec.yaml.decode(f.read())
    reconstructed_spec = ProcessSpec.model_validate(loaded["plugboard"]["process"])
    assert len(reconstructed_spec.args.components) == 2
    assert reconstructed_spec.args.state.type == "plugboard.state.DictStateBackend"
    assert reconstructed_spec.args.parameters == {}
