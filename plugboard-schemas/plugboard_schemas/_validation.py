"""Validation utilities for process topology.

Provides functions to validate process topology including:
- Checking that all component inputs are connected
- Checking that input events have matching output event producers
- Checking for circular connections that require initial values

All validators accept the output of ``process.dict()`` or the relevant
sub-structures thereof.
"""

from __future__ import annotations

from collections import defaultdict
import typing as _t

from ._graph import simple_cycles
from ._validator_registry import validator


def _build_component_graph(
    connectors: dict[str, dict[str, _t.Any]],
) -> dict[str, set[str]]:
    """Build a directed graph of component connections from connector dicts.

    Args:
        connectors: Dictionary mapping connector IDs to connector dicts,
            as returned by ``process.dict()["connectors"]``.

    Returns:
        A dictionary mapping source component names to sets of target component names.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for conn_info in connectors.values():
        spec = conn_info["spec"]
        source_entity = spec["source"]["entity"]
        target_entity = spec["target"]["entity"]
        if source_entity != target_entity:
            graph[source_entity].add(target_entity)
            if target_entity not in graph:
                graph[target_entity] = set()
    return dict(graph)


def _get_edges_in_cycle(
    cycle: list[str],
    connectors: dict[str, dict[str, _t.Any]],
) -> list[dict[str, _t.Any]]:
    """Get all connector spec dicts that form edges within a cycle.

    Args:
        cycle: List of component names forming a cycle.
        connectors: Dictionary mapping connector IDs to connector dicts.

    Returns:
        List of connector spec dicts that are part of the cycle.
    """
    conn_map: dict[tuple[str, str], dict[str, _t.Any]] = {
        (spec["source"]["entity"], spec["target"]["entity"]): spec
        for conn_info in connectors.values()
        if (spec := conn_info["spec"])
    }
    cycle_edges: list[dict[str, _t.Any]] = []
    for i, node in enumerate(cycle):
        next_node = cycle[(i + 1) % len(cycle)]
        try:
            spec = conn_map[(node, next_node)]
        except KeyError:
            raise ValueError(f"Cycle edge not found: {node} -> {next_node}")
        cycle_edges.append(spec)
    return cycle_edges


@validator
def validate_all_inputs_connected(
    process_dict: dict[str, _t.Any],
) -> list[str]:
    """Check that all component inputs are connected.

    Args:
        process_dict: The output of ``process.dict()``.  Uses the ``"components"``
            and ``"connectors"`` keys.

    Returns:
        List of error messages for unconnected inputs.
    """
    components: dict[str, dict[str, _t.Any]] = process_dict["components"]
    connectors: dict[str, dict[str, _t.Any]] = process_dict["connectors"]

    connected_inputs: dict[str, set[str]] = defaultdict(set)
    for conn_info in connectors.values():
        spec = conn_info["spec"]
        target_name = spec["target"]["entity"]
        target_field = spec["target"]["descriptor"]
        connected_inputs[target_name].add(target_field)

    errors: list[str] = []
    for comp_name, comp_data in components.items():
        io = comp_data.get("io", {})
        all_inputs = set(io.get("inputs", []))
        connected = connected_inputs.get(comp_name, set())
        unconnected = all_inputs - connected
        if unconnected:
            errors.append(f"Component '{comp_name}' has unconnected inputs: {sorted(unconnected)}")
    return errors


@validator
def validate_input_events(
    process_dict: dict[str, _t.Any],
) -> list[str]:
    """Check that all components with input events have a matching output event producer.

    Args:
        process_dict: The output of ``process.dict()``.  Uses the ``"components"`` key.

    Returns:
        List of error messages for unmatched input events.
    """
    components: dict[str, dict[str, _t.Any]] = process_dict["components"]

    all_output_events: set[str] = set()
    for comp_data in components.values():
        io = comp_data.get("io", {})
        all_output_events.update(io.get("output_events", []))

    errors: list[str] = []
    for comp_name, comp_data in components.items():
        io = comp_data.get("io", {})
        input_events = set(io.get("input_events", []))
        unmatched = input_events - all_output_events
        if unmatched:
            errors.append(
                f"Component '{comp_name}' has input events with no producer: {sorted(unmatched)}"
            )
    return errors


@validator
def validate_no_unresolved_cycles(
    process_dict: dict[str, _t.Any],
) -> list[str]:
    """Check for circular connections that are not resolved by initial values.

    Circular loops are only valid if there are ``initial_values`` set on an
    appropriate component input within the loop.

    Args:
        process_dict: The output of ``process.dict()``.  Uses the ``"components"``
            and ``"connectors"`` keys.

    Returns:
        List of error messages for unresolved circular connections.
    """
    components: dict[str, dict[str, _t.Any]] = process_dict["components"]
    connectors: dict[str, dict[str, _t.Any]] = process_dict["connectors"]

    graph = _build_component_graph(connectors)
    if not graph:
        return []

    # Build lookup of component initial_values by name
    initial_values_by_comp: dict[str, set[str]] = {}
    for comp_name, comp_data in components.items():
        io = comp_data.get("io", {})
        iv = io.get("initial_values", {})
        if iv:
            initial_values_by_comp[comp_name] = set(iv.keys())

    errors: list[str] = []
    for cycle in simple_cycles(graph):
        cycle_edges = _get_edges_in_cycle(cycle, connectors)
        cycle_resolved = False
        for edge in cycle_edges:
            target_comp = edge["target"]["entity"]
            target_field = edge["target"]["descriptor"]
            if target_comp in initial_values_by_comp:
                if target_field in initial_values_by_comp[target_comp]:
                    cycle_resolved = True
                    break
        if not cycle_resolved:
            cycle_str = " -> ".join(cycle + [cycle[0]])
            errors.append(
                f"Circular connection detected without initial values: {cycle_str}. "
                f"Set initial_values on a component input within the loop to resolve."
            )
    return errors
