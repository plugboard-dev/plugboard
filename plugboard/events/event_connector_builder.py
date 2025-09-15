"""Provides `EventConnectorBuilder` class which helps build event connectors for components."""

from __future__ import annotations

import typing as _t

from plugboard.connector import Connector
from plugboard.events.event import Event
from plugboard.schemas import ConnectorMode, ConnectorSocket, ConnectorSpec


if _t.TYPE_CHECKING:
    from plugboard.component import Component
    from plugboard.connector import ConnectorBuilder


class EventConnectorBuilder:  # pragma: no cover
    """`EventConnectorBuilder` constructs connectors for component event handlers."""

    _source_descriptor: str = "publishers"
    _target_descriptor: str = "subscribers"

    def __init__(self, connector_builder: ConnectorBuilder) -> None:
        self._connector_builder = connector_builder

    def build(self, components: _t.Iterable[Component]) -> dict[str, Connector]:
        """Returns mapping of connectors for events handled by components."""
        evt_conn_map: dict[str, Connector] = {}
        for component in components:
            comp_evt_conn_map = self._build_for_component(evt_conn_map, component)
            evt_conn_map.update(comp_evt_conn_map)
        return evt_conn_map

    def _build_for_component(
        self, evt_conn_map: dict[str, Connector], component: Component
    ) -> dict[str, Connector]:
        component_evts = set(component.io.input_events + component.io.output_events)
        return {
            evt.type: self._build_for_event(evt.type)
            for evt in component_evts
            if evt.type not in evt_conn_map
        }

    def _build_for_event(self, evt_type: str) -> Connector:
        evt_type_safe = Event.safe_type(evt_type)
        source = ConnectorSocket(entity=evt_type_safe, descriptor=self._source_descriptor)
        target = ConnectorSocket(entity=evt_type_safe, descriptor=self._target_descriptor)
        spec = ConnectorSpec(source=source, target=target, mode=ConnectorMode.PUBSUB)
        return self._connector_builder.build(spec)
