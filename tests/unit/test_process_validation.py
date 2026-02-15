"""Tests for process topology validation."""

from plugboard_schemas import (
    ProcessSpec,
    validate_all_inputs_connected,
    validate_input_events,
)
from plugboard_schemas._graph import simple_cycles
import pytest


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
# Tests for validate_no_unresolved_cycles
# ---------------------------------------------------------------------------


class TestValidateNoUnresolvedCycles:
    """Tests for circular connection validation."""

    @staticmethod
    def _make_component(name: str, type_: str = "some.Component", **kwargs: object) -> dict:
        args: dict = {"name": name}
        args.update(kwargs)
        return {"type": type_, "args": args}

    @staticmethod
    def _make_connector(source: str, target: str) -> dict:
        return {"source": source, "target": target}

    def test_no_cycles_passes(self) -> None:
        """Linear topology passes validation."""
        spec = ProcessSpec.model_validate(
            {
                "args": {
                    "components": [
                        self._make_component("a"),
                        self._make_component("b"),
                        self._make_component("c"),
                    ],
                    "connectors": [
                        self._make_connector("a.out", "b.in_1"),
                        self._make_connector("b.out", "c.in_1"),
                    ],
                }
            }
        )
        assert spec is not None

    def test_cycle_without_initial_values_fails(self) -> None:
        """Cycle without initial_values raises ValueError."""
        with pytest.raises(ValueError, match="Circular connection detected"):
            ProcessSpec.model_validate(
                {
                    "args": {
                        "components": [
                            self._make_component("a"),
                            self._make_component("b"),
                        ],
                        "connectors": [
                            self._make_connector("a.out", "b.in_1"),
                            self._make_connector("b.out", "a.in_1"),
                        ],
                    }
                }
            )

    def test_cycle_with_initial_values_passes(self) -> None:
        """Cycle with initial_values on a target input passes."""
        spec = ProcessSpec.model_validate(
            {
                "args": {
                    "components": [
                        self._make_component("a", initial_values={"in_1": [0]}),
                        self._make_component("b"),
                    ],
                    "connectors": [
                        self._make_connector("a.out", "b.in_1"),
                        self._make_connector("b.out", "a.in_1"),
                    ],
                }
            }
        )
        assert spec is not None

    def test_cycle_with_initial_values_on_other_field_fails(self) -> None:
        """Cycle with initial_values on an unrelated field still fails."""
        with pytest.raises(ValueError, match="Circular connection detected"):
            ProcessSpec.model_validate(
                {
                    "args": {
                        "components": [
                            self._make_component("a", initial_values={"other": [0]}),
                            self._make_component("b"),
                        ],
                        "connectors": [
                            self._make_connector("a.out", "b.in_1"),
                            self._make_connector("b.out", "a.in_1"),
                        ],
                    }
                }
            )

    def test_three_node_cycle_without_initial_values_fails(self) -> None:
        """Three-node cycle without initial_values raises ValueError."""
        with pytest.raises(ValueError, match="Circular connection detected"):
            ProcessSpec.model_validate(
                {
                    "args": {
                        "components": [
                            self._make_component("a"),
                            self._make_component("b"),
                            self._make_component("c"),
                        ],
                        "connectors": [
                            self._make_connector("a.out", "b.in_1"),
                            self._make_connector("b.out", "c.in_1"),
                            self._make_connector("c.out", "a.in_1"),
                        ],
                    }
                }
            )

    def test_three_node_cycle_with_initial_values_passes(self) -> None:
        """Three-node cycle with initial_values on any target input passes."""
        spec = ProcessSpec.model_validate(
            {
                "args": {
                    "components": [
                        self._make_component("a"),
                        self._make_component("b", initial_values={"in_1": [0]}),
                        self._make_component("c"),
                    ],
                    "connectors": [
                        self._make_connector("a.out", "b.in_1"),
                        self._make_connector("b.out", "c.in_1"),
                        self._make_connector("c.out", "a.in_1"),
                    ],
                }
            }
        )
        assert spec is not None

    def test_no_connectors_passes(self) -> None:
        """Process with no connectors passes validation."""
        spec = ProcessSpec.model_validate(
            {
                "args": {
                    "components": [self._make_component("a")],
                }
            }
        )
        assert spec is not None


# ---------------------------------------------------------------------------
# Tests for validate_all_inputs_connected (runtime utility)
# ---------------------------------------------------------------------------


class TestValidateAllInputsConnected:
    """Tests for the all-inputs-connected validation utility."""

    @staticmethod
    def _conn(source: str, target: str) -> dict:
        return {"source": source, "target": target}

    def test_all_connected(self) -> None:
        """Test that validation passes when all inputs are connected."""
        from typing import Any

        from plugboard_schemas import ConnectorSpec

        components: dict[str, dict[str, Any]] = {
            "a": {"inputs": []},
            "b": {"inputs": ["in_1"]},
        }
        connectors = [ConnectorSpec.model_validate(self._conn("a.out", "b.in_1"))]
        errors = validate_all_inputs_connected(components, connectors)
        assert errors == []

    def test_missing_input(self) -> None:
        """Test that validation fails when an input is not connected."""
        from typing import Any

        from plugboard_schemas import ConnectorSpec

        components: dict[str, dict[str, Any]] = {
            "a": {"inputs": []},
            "b": {"inputs": ["in_1", "in_2"]},
        }
        connectors = [ConnectorSpec.model_validate(self._conn("a.out", "b.in_1"))]
        errors = validate_all_inputs_connected(components, connectors)
        assert len(errors) == 1
        assert "in_2" in errors[0]

    def test_no_inputs_no_errors(self) -> None:
        """Test that validation passes when components have no inputs."""
        from typing import Any

        from plugboard_schemas import ConnectorSpec

        components: dict[str, dict[str, Any]] = {"a": {"inputs": []}}
        connectors: list[ConnectorSpec] = []
        errors = validate_all_inputs_connected(components, connectors)
        assert errors == []


# ---------------------------------------------------------------------------
# Tests for validate_input_events (runtime utility)
# ---------------------------------------------------------------------------


class TestValidateInputEvents:
    """Tests for the input-events validation utility."""

    def test_matched_events(self) -> None:
        """Test that validation passes when all input events have producers."""
        from typing import Any

        components: dict[str, dict[str, Any]] = {
            "clock": {"input_events": [], "output_events": ["tick"]},
            "ctrl": {"input_events": ["tick"], "output_events": []},
        }
        errors = validate_input_events(components)
        assert errors == []

    def test_unmatched_event(self) -> None:
        """Test that validation fails when input events have no producer."""
        from typing import Any

        components: dict[str, dict[str, Any]] = {
            "ctrl": {"input_events": ["tick"], "output_events": []},
        }
        errors = validate_input_events(components)
        assert len(errors) == 1
        assert "tick" in errors[0]

    def test_no_events(self) -> None:
        """Test that validation passes when components have no events."""
        from typing import Any

        components: dict[str, dict[str, Any]] = {
            "a": {"input_events": [], "output_events": []},
        }
        errors = validate_input_events(components)
        assert errors == []

    def test_multiple_unmatched(self) -> None:
        """Test that validation correctly identifies unmatched events."""
        from typing import Any

        components: dict[str, dict[str, Any]] = {
            "a": {"input_events": ["evt_x", "evt_y"], "output_events": []},
            "b": {"input_events": [], "output_events": ["evt_x"]},
        }
        errors = validate_input_events(components)
        assert len(errors) == 1
        assert "evt_y" in errors[0]
