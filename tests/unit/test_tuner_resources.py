"""Unit tests for Tuner resource placement calculations."""
# ruff: noqa: D101,D102,D103

from plugboard_schemas import (
    ComponentArgsSpec,
    ComponentSpec,
    ProcessArgsSpec,
    ProcessSpec,
    Resource,
)


def test_process_spec_with_component_resources() -> None:
    """Test ProcessSpec can include component resources."""
    component_spec = ComponentSpec(
        type="test.Component",
        args=ComponentArgsSpec(
            name="test_component",
            resources=Resource(cpu="500m", gpu=1, memory="100Mi"),
        ),
    )

    process_spec = ProcessSpec(
        type="plugboard.process.LocalProcess",
        args=ProcessArgsSpec(
            name="test_process",
            components=[component_spec],
            connectors=[],
        ),
    )

    # Verify the resource is properly nested in the spec
    assert process_spec.args.components[0].args.resources is not None
    assert process_spec.args.components[0].args.resources.cpu == 0.5
    assert process_spec.args.components[0].args.resources.gpu == 1.0
    assert process_spec.args.components[0].args.resources.memory == 100 * 1024 * 1024


def test_process_spec_with_multiple_component_resources() -> None:
    """Test ProcessSpec with multiple components having resources."""
    component1 = ComponentSpec(
        type="test.Component1",
        args=ComponentArgsSpec(
            name="comp1",
            resources=Resource(cpu=1.0, gpu=0.5),
        ),
    )

    component2 = ComponentSpec(
        type="test.Component2",
        args=ComponentArgsSpec(
            name="comp2",
            resources=Resource(cpu=2.0, memory="50Mi"),
        ),
    )

    process_spec = ProcessSpec(
        type="plugboard.process.LocalProcess",
        args=ProcessArgsSpec(
            name="test_process",
            components=[component1, component2],
            connectors=[],
        ),
    )

    # Verify both components have resources
    assert process_spec.args.components[0].args.resources.cpu == 1.0
    assert process_spec.args.components[0].args.resources.gpu == 0.5
    assert process_spec.args.components[1].args.resources.cpu == 2.0
    assert process_spec.args.components[1].args.resources.memory == 50 * 1024 * 1024


def test_process_spec_with_default_component_resources() -> None:
    """Test ProcessSpec with component using default resources."""
    component_spec = ComponentSpec(
        type="test.Component",
        args=ComponentArgsSpec(
            name="test_component",
            # No resources specified, should use defaults
        ),
    )

    process_spec = ProcessSpec(
        type="plugboard.process.LocalProcess",
        args=ProcessArgsSpec(
            name="test_process",
            components=[component_spec],
            connectors=[],
        ),
    )

    # Resources should be None when not specified
    assert process_spec.args.components[0].args.resources is None
