"""Validation utilities for `ProcessSpec` objects.

Provides functions to validate process topology including:
- Checking that all component inputs are connected
- Checking that input events have matching output event producers
- Checking for circular connections that require initial values
"""

from __future__ import annotations

from collections import defaultdict
import typing as _t

from ._graph import simple_cycles


if _t.TYPE_CHECKING:
    from .component import ComponentSpec
    from .connector import ConnectorSpec


def _build_component_graph(
    connectors: list[ConnectorSpec],
) -> dict[str, set[str]]:
    """Build a directed graph of component connections from connector specs.

    Args:
        connectors: List of connector specifications.

    Returns:
        A dictionary mapping source component names to sets of target component names.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for conn in connectors:
        source_entity = conn.source.entity
        target_entity = conn.target.entity
        if source_entity != target_entity:
            graph[source_entity].add(target_entity)
            # Ensure target is in graph even with no outgoing edges
            if target_entity not in graph:
                graph[target_entity] = set()
    return dict(graph)


def _get_edges_in_cycle(
    cycle: list[str],
    connectors: list[ConnectorSpec],
) -> list[ConnectorSpec]:
    """Get all connector specs that form edges within a cycle.

    Args:
        cycle: List of component names forming a cycle.
        connectors: All connector specifications.

    Returns:
        List of connector specs that are part of the cycle.
    """
    cycle_edges: list[ConnectorSpec] = []
    for i, node in enumerate(cycle):
        next_node = cycle[(i + 1) % len(cycle)]
        for conn in connectors:
            if conn.source.entity == node and conn.target.entity == next_node:
                cycle_edges.append(conn)
    return cycle_edges


def validate_all_inputs_connected(
    components: dict[str, dict[str, _t.Any]],
    connectors: list[ConnectorSpec],
) -> list[str]:
    """Check that all component inputs are connected.

    Args:
        components: Dictionary mapping component names to their IO info.
            Each value must have an ``"inputs"`` key with a list of input field names.
        connectors: List of connector specifications.

    Returns:
        List of error messages for unconnected inputs.
    """
    # Build mapping of which component inputs are connected
    connected_inputs: dict[str, set[str]] = defaultdict(set)
    for conn in connectors:
        target_name = conn.target.entity
        target_field = conn.target.descriptor
        connected_inputs[target_name].add(target_field)

    errors: list[str] = []
    for comp_name, comp_info in components.items():
        all_inputs = set(comp_info.get("inputs", []))
        connected = connected_inputs.get(comp_name, set())
        unconnected = all_inputs - connected
        if unconnected:
            errors.append(f"Component '{comp_name}' has unconnected inputs: {sorted(unconnected)}")
    return errors


def validate_input_events(
    components: dict[str, dict[str, _t.Any]],
) -> list[str]:
    """Check that all components with input events have a matching output event producer.

    Args:
        components: Dictionary mapping component names to their IO info.
            Each value must have ``"input_events"`` and ``"output_events"`` keys
            with lists of event type strings.

    Returns:
        List of error messages for unmatched input events.
    """
    # Collect all output event types across all components
    all_output_events: set[str] = set()
    for comp_info in components.values():
        all_output_events.update(comp_info.get("output_events", []))

    errors: list[str] = []
    for comp_name, comp_info in components.items():
        input_events = set(comp_info.get("input_events", []))
        unmatched = input_events - all_output_events
        if unmatched:
            errors.append(
                f"Component '{comp_name}' has input events with no producer: {sorted(unmatched)}"
            )
    return errors


def validate_no_unresolved_cycles(
    components: list[ComponentSpec],
    connectors: list[ConnectorSpec],
) -> list[str]:
    """Check for circular connections that are not resolved by initial values.

    Circular loops are only valid if there are ``initial_values`` set on an
    appropriate component input within the loop.

    Args:
        components: List of component specifications.
        connectors: List of connector specifications.

    Returns:
        List of error messages for unresolved circular connections.
    """
    graph = _build_component_graph(connectors)
    if not graph:
        return []

    # Build lookup of component initial_values by name
    initial_values_by_comp: dict[str, set[str]] = {}
    for comp in components:
        if comp.args.initial_values:
            initial_values_by_comp[comp.args.name] = set(comp.args.initial_values.keys())

    errors: list[str] = []
    for cycle in simple_cycles(graph):
        # Check if any edge in the cycle targets a component input with initial_values
        cycle_edges = _get_edges_in_cycle(cycle, connectors)
        cycle_resolved = False
        for edge in cycle_edges:
            target_comp = edge.target.entity
            target_field = edge.target.descriptor
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
