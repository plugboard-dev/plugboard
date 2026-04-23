"""Tests for process topology validation."""

import typing as _t

from plugboard_schemas import (
    validate_all_inputs_connected,
    validate_input_events,
    validate_no_unresolved_cycles,
    validate_process,
)
from plugboard_schemas._graph import simple_cycles


# ---------------------------------------------------------------------------
# Tests for simple_cycles (Johnson's algorithm)
# ---------------------------------------------------------------------------


class TestSimpleCycles:
    """Tests for Johnson's cycle-finding algorithm."""

    def test_no_cycles(self) -> None:
        """A DAG has no cycles."""
        graph: dict[str, set[str]] = {"a": {"b"}, "b": {"c"}, "c": set()}
        assert list(simple_cycles(graph)) == []

    def test_single_self_loop(self) -> None:
        """A self-loop is a cycle of length 1."""
        graph: dict[str, set[str]] = {"a": {"a"}}
        cycles = list(simple_cycles(graph))
        assert len(cycles) == 1
        assert cycles[0] == ["a"]

    def test_simple_two_node_cycle(self) -> None:
        """Two nodes forming a cycle."""
        graph: dict[str, set[str]] = {"a": {"b"}, "b": {"a"}}
        cycles = list(simple_cycles(graph))
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}

    def test_three_node_cycle(self) -> None:
        """Three nodes forming a single cycle."""
        graph: dict[str, set[str]] = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        cycles = list(simple_cycles(graph))
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b", "c"}

    def test_multiple_cycles(self) -> None:
        """Graph with multiple distinct cycles."""
        graph: dict[str, set[str]] = {
            "a": {"b"},
            "b": {"a", "c"},
            "c": {"d"},
            "d": {"c"},
        }
        cycles = list(simple_cycles(graph))
        cycle_sets = [frozenset(c) for c in cycles]
        assert frozenset({"a", "b"}) in cycle_sets
        assert frozenset({"c", "d"}) in cycle_sets

    def test_empty_graph(self) -> None:
        """Empty graph has no cycles."""
        graph: dict[str, set[str]] = {}
        assert list(simple_cycles(graph)) == []

    def test_disconnected_graph(self) -> None:
        """Disconnected graph with no cycles."""
        graph: dict[str, set[str]] = {"a": set(), "b": set(), "c": set()}
        assert list(simple_cycles(graph)) == []

    def test_complex_graph(self) -> None:
        """Complex graph with overlapping cycles."""
        graph: dict[str, set[str]] = {
            "a": {"b"},
            "b": {"c"},
            "c": {"a", "d"},
            "d": {"b"},
        }
        cycles = list(simple_cycles(graph))
        # Should find cycles: a->b->c->a and b->c->d->b
        assert len(cycles) >= 2
        cycle_sets = [frozenset(c) for c in cycles]
        assert frozenset({"a", "b", "c"}) in cycle_sets
        assert frozenset({"b", "c", "d"}) in cycle_sets


# ---------------------------------------------------------------------------
# Helpers for building process.dict()-style data structures
# ---------------------------------------------------------------------------


def _make_component(
    name: str,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    input_events: list[str] | None = None,
    output_events: list[str] | None = None,
    initial_values: dict[str, _t.Any] | None = None,
) -> dict[str, _t.Any]:
    """Build a component dict matching process.dict() format."""
    return {
        "id": name,
        "name": name,
        "status": "created",
        "io": {
            "namespace": name,
            "inputs": inputs or [],
            "outputs": outputs or [],
            "input_events": input_events or [],
            "output_events": output_events or [],
            "initial_values": initial_values or {},
        },
    }


def _make_connector(source: str, target: str) -> dict[str, _t.Any]:
    """Build a connector dict matching process.dict() format."""
    src_entity, src_desc = source.split(".")
    tgt_entity, tgt_desc = target.split(".")
    conn_id = f"{source}..{target}"
    return {
        conn_id: {
            "id": conn_id,
            "spec": {
                "source": {"entity": src_entity, "descriptor": src_desc},
                "target": {"entity": tgt_entity, "descriptor": tgt_desc},
                "mode": "pipeline",
            },
        }
    }


def _make_process_dict(
    components: dict[str, dict[str, _t.Any]],
    connectors: dict[str, dict[str, _t.Any]] | None = None,
) -> dict[str, _t.Any]:
    """Build a process dict matching process.dict() format."""
    return {
        "id": "test_process",
        "name": "test_process",
        "status": "created",
        "components": components,
        "connectors": connectors or {},
        "parameters": {},
    }


# ---------------------------------------------------------------------------
# Tests for validate_no_unresolved_cycles
# ---------------------------------------------------------------------------


class TestValidateNoUnresolvedCycles:
    """Tests for circular connection validation."""

    def test_no_cycles_passes(self) -> None:
        """Linear topology passes validation."""
        connectors = {**_make_connector("a.out", "b.in_1"), **_make_connector("b.out", "c.in_1")}
        pd = _make_process_dict(
            components={
                "a": _make_component("a", outputs=["out"]),
                "b": _make_component("b", inputs=["in_1"], outputs=["out"]),
                "c": _make_component("c", inputs=["in_1"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert errors == []

    def test_cycle_without_initial_values_fails(self) -> None:
        """Cycle without initial_values returns errors."""
        connectors = {**_make_connector("a.out", "b.in_1"), **_make_connector("b.out", "a.in_1")}
        pd = _make_process_dict(
            components={
                "a": _make_component("a", inputs=["in_1"], outputs=["out"]),
                "b": _make_component("b", inputs=["in_1"], outputs=["out"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert len(errors) == 1
        assert "Circular connection detected" in errors[0]

    def test_cycle_with_initial_values_passes(self) -> None:
        """Cycle with initial_values on a target input passes."""
        connectors = {**_make_connector("a.out", "b.in_1"), **_make_connector("b.out", "a.in_1")}
        pd = _make_process_dict(
            components={
                "a": _make_component(
                    "a", inputs=["in_1"], outputs=["out"], initial_values={"in_1": [0]}
                ),
                "b": _make_component("b", inputs=["in_1"], outputs=["out"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert errors == []

    def test_cycle_with_initial_values_on_other_field_fails(self) -> None:
        """Cycle with initial_values on an unrelated field still fails."""
        connectors = {**_make_connector("a.out", "b.in_1"), **_make_connector("b.out", "a.in_1")}
        pd = _make_process_dict(
            components={
                "a": _make_component(
                    "a", inputs=["in_1"], outputs=["out"], initial_values={"other": [0]}
                ),
                "b": _make_component("b", inputs=["in_1"], outputs=["out"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert len(errors) == 1
        assert "Circular connection detected" in errors[0]

    def test_three_node_cycle_without_initial_values_fails(self) -> None:
        """Three-node cycle without initial_values returns errors."""
        connectors = {
            **_make_connector("a.out", "b.in_1"),
            **_make_connector("b.out", "c.in_1"),
            **_make_connector("c.out", "a.in_1"),
        }
        pd = _make_process_dict(
            components={
                "a": _make_component("a", inputs=["in_1"], outputs=["out"]),
                "b": _make_component("b", inputs=["in_1"], outputs=["out"]),
                "c": _make_component("c", inputs=["in_1"], outputs=["out"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert len(errors) == 1
        assert "Circular connection detected" in errors[0]

    def test_three_node_cycle_with_initial_values_passes(self) -> None:
        """Three-node cycle with initial_values on any target input passes."""
        connectors = {
            **_make_connector("a.out", "b.in_1"),
            **_make_connector("b.out", "c.in_1"),
            **_make_connector("c.out", "a.in_1"),
        }
        pd = _make_process_dict(
            components={
                "a": _make_component("a", inputs=["in_1"], outputs=["out"]),
                "b": _make_component(
                    "b", inputs=["in_1"], outputs=["out"], initial_values={"in_1": [0]}
                ),
                "c": _make_component("c", inputs=["in_1"], outputs=["out"]),
            },
            connectors=connectors,
        )
        errors = validate_no_unresolved_cycles(pd)
        assert errors == []

    def test_no_connectors_passes(self) -> None:
        """Process with no connectors passes validation."""
        pd = _make_process_dict(
            components={"a": _make_component("a")},
        )
        errors = validate_no_unresolved_cycles(pd)
        assert errors == []


# ---------------------------------------------------------------------------
# Tests for validate_all_inputs_connected
# ---------------------------------------------------------------------------


class TestValidateAllInputsConnected:
    """Tests for the all-inputs-connected validation utility."""

    def test_all_connected(self) -> None:
        """Test that validation passes when all inputs are connected."""
        connectors = _make_connector("a.out", "b.in_1")
        pd = _make_process_dict(
            components={
                "a": _make_component("a", outputs=["out"]),
                "b": _make_component("b", inputs=["in_1"]),
            },
            connectors=connectors,
        )
        errors = validate_all_inputs_connected(pd)
        assert errors == []

    def test_missing_input(self) -> None:
        """Test that validation fails when an input is not connected."""
        connectors = _make_connector("a.out", "b.in_1")
        pd = _make_process_dict(
            components={
                "a": _make_component("a", outputs=["out"]),
                "b": _make_component("b", inputs=["in_1", "in_2"]),
            },
            connectors=connectors,
        )
        errors = validate_all_inputs_connected(pd)
        assert len(errors) == 1
        assert "in_2" in errors[0]

    def test_no_inputs_no_errors(self) -> None:
        """Test that validation passes when components have no inputs."""
        pd = _make_process_dict(
            components={"a": _make_component("a")},
        )
        errors = validate_all_inputs_connected(pd)
        assert errors == []

    def test_missing_inputs_allowed_for_event_driven_component_reuse(self) -> None:
        """Unconnected inputs are allowed when non-system input events can populate them."""
        pd = _make_process_dict(
            components={
                "producer": _make_component("producer", output_events=["message_event"]),
                "writer": _make_component(
                    "writer",
                    inputs=["message"],
                    input_events=["system_stop", "message_event"],
                ),
            },
        )
        errors = validate_all_inputs_connected(pd)
        assert errors == []


# ---------------------------------------------------------------------------
# Tests for validate_input_events
# ---------------------------------------------------------------------------


class TestValidateInputEvents:
    """Tests for the input-events validation utility."""

    def test_matched_events(self) -> None:
        """Test that validation passes when all input events have producers."""
        pd = _make_process_dict(
            components={
                "clock": _make_component("clock", output_events=["tick"]),
                "ctrl": _make_component("ctrl", input_events=["tick"]),
            },
        )
        errors = validate_input_events(pd)
        assert errors == []

    def test_unmatched_event(self) -> None:
        """Test that validation fails when input events have no producer."""
        pd = _make_process_dict(
            components={
                "ctrl": _make_component("ctrl", input_events=["tick"]),
            },
        )
        errors = validate_input_events(pd)
        assert len(errors) == 1
        assert "tick" in errors[0]

    def test_no_events(self) -> None:
        """Test that validation passes when components have no events."""
        pd = _make_process_dict(
            components={"a": _make_component("a")},
        )
        errors = validate_input_events(pd)
        assert errors == []

    def test_multiple_unmatched(self) -> None:
        """Test that validation correctly identifies unmatched events."""
        pd = _make_process_dict(
            components={
                "a": _make_component("a", input_events=["evt_x", "evt_y"]),
                "b": _make_component("b", output_events=["evt_x"]),
            },
        )
        errors = validate_input_events(pd)
        assert len(errors) == 1
        assert "evt_y" in errors[0]


# ---------------------------------------------------------------------------
# Tests for validate_process (combined validator)
# ---------------------------------------------------------------------------


class TestValidateProcess:
    """Tests for the combined validate_process utility."""

    def test_valid_process(self) -> None:
        """Test that a valid process returns no errors."""
        connectors = _make_connector("a.out_1", "b.in_1")
        pd = _make_process_dict(
            components={
                "a": _make_component("a", outputs=["out_1"]),
                "b": _make_component("b", inputs=["in_1"]),
            },
            connectors=connectors,
        )
        errors = validate_process(pd)
        assert errors == []

    def test_multiple_errors(self) -> None:
        """Test that multiple validation errors are collected."""
        pd = _make_process_dict(
            components={
                "a": _make_component("a", inputs=["in_1"], input_events=["missing_evt"]),
            },
        )
        errors = validate_process(pd)
        # Should have at least: unconnected input + unmatched event
        assert len(errors) >= 2
