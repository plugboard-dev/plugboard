"""Provides `EventConnectorSpecBuilder` utility class which builds event connector specs for components."""  # noqa: E501,W505

from __future__ import annotations

import typing as _t

from plugboard.events.event import Event
from plugboard.schemas import ConnectorMode, ConnectorSocket, ConnectorSpec


if _t.TYPE_CHECKING:
    from plugboard.component import Component


class EventConnectorSpecBuilder:  # pragma: no cover
    """`EventConnectorSpecBuilder` constructs connector specs for component event handlers."""

    _source_descriptor: str = "publishers"
    _target_descriptor: str = "subscribers"

    @staticmethod
    def build(components: _t.Iterable[Component]) -> dict[str, ConnectorSpec]:
        """Returns mapping of connector specs for events handled by components."""
        evt_conn_map: dict[str, ConnectorSpec] = {}
        for component in components:
            comp_evt_conn_map = EventConnectorSpecBuilder._build_for_component(
                evt_conn_map, component
            )
            evt_conn_map.update(comp_evt_conn_map)
        return evt_conn_map

    @staticmethod
    def _build_for_component(
        evt_conn_map: dict[str, ConnectorSpec], component: Component
    ) -> dict[str, ConnectorSpec]:
        component_evts = set(component.io.input_events + component.io.output_events)
        return {
            evt.type: EventConnectorSpecBuilder._build_for_event(evt.type)
            for evt in component_evts
            if evt.type not in evt_conn_map
        }

    @staticmethod
    def _build_for_event(evt_type: str) -> ConnectorSpec:
        evt_type_safe = Event.safe_type(evt_type)
        source = ConnectorSocket(
            entity=evt_type_safe, descriptor=EventConnectorSpecBuilder._source_descriptor
        )
        target = ConnectorSocket(
            entity=evt_type_safe, descriptor=EventConnectorSpecBuilder._target_descriptor
        )
        spec = ConnectorSpec(source=source, target=target, mode=ConnectorMode.PUBSUB)
        return spec
