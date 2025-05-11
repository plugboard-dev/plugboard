"""Provides `ProcessBuilder` to build `Process` objects."""

import os
from pydoc import locate
import typing as _t

from plugboard.component.component import Component, ComponentRegistry
from plugboard.connector.connector import Connector
from plugboard.connector.connector_builder import ConnectorBuilder
from plugboard.events.event_connector_builder import EventConnectorBuilder
from plugboard.process.process import Process
from plugboard.schemas import ProcessSpec, StateBackendSpec
from plugboard.state import StateBackend
from plugboard.utils import DI


class ProcessBuilder:
    """Builds `Process` objects."""

    @classmethod
    def build(cls, spec: ProcessSpec) -> Process:
        """Build a `Process` object.

        Args:
            spec: A `ProcessSpec` object defining the `Process`.

        Returns:
            A `Process` object.
        """
        state = cls._build_statebackend(spec)
        components = cls._build_components(spec)
        connectors = cls._build_connectors(spec, components)
        process_class: _t.Optional[_t.Any] = locate(spec.type)
        if not process_class or not issubclass(process_class, Process):
            raise ValueError(f"Process class {spec.type} not found.")

        return process_class(
            components=components,
            connectors=connectors,
            name=spec.args.name,
            parameters=spec.args.parameters,
            state=state,
        )

    @classmethod
    def _build_statebackend(cls, spec: ProcessSpec) -> StateBackend:
        state_spec = spec.args.state
        statebackend_class: _t.Optional[_t.Any] = locate(state_spec.type)
        if not statebackend_class or not issubclass(statebackend_class, StateBackend):
            raise ValueError(f"StateBackend class {spec.args.state.type} not found.")
        cls._handle_job_id(state_spec)
        return statebackend_class(**dict(spec.args.state.args))

    @classmethod
    def _handle_job_id(cls, state_spec: StateBackendSpec) -> None:
        """Handle job ID for the state backend.

        If a job ID is provided in the state spec, it will be set as an environment variable.
        If the job ID is already set in the environment, it will be checked against the one in the
        state spec. If they do not match, a RuntimeError will be raised.
        """
        if state_spec.args.job_id is None:
            return
        if (
            env_job_id := os.environ.get("PLUGBOARD_JOB_ID")
        ) is not None and env_job_id != state_spec.args.job_id:
            raise RuntimeError(
                f"Job ID {state_spec.args.job_id} does not match environment variable "
                f"PLUGBOARD_JOB_ID={env_job_id}"
            )
        os.environ["PLUGBOARD_JOB_ID"] = state_spec.args.job_id

    @classmethod
    def _build_components(cls, spec: ProcessSpec) -> list[Component]:
        for c in spec.args.components:
            component_class: _t.Optional[_t.Any] = locate(c.type)
            if not component_class or not issubclass(component_class, Component):
                raise ValueError(f"Component class {c.type} not found.")
        return [ComponentRegistry.build(c.type, **dict(c.args)) for c in spec.args.components]

    @classmethod
    def _build_connectors(cls, spec: ProcessSpec, components: list[Component]) -> list[Connector]:
        connector_class: _t.Optional[_t.Any] = locate(spec.connector_builder.type)
        if not connector_class or not issubclass(connector_class, Connector):
            raise ValueError(f"Connector class {spec.connector_builder.type} not found")
        connector_builder = ConnectorBuilder(
            connector_cls=connector_class, **dict(spec.connector_builder.args)
        )
        event_connector_builder = EventConnectorBuilder(connector_builder=connector_builder)
        # TODO: Remove this when https://github.com/plugboard-dev/plugboard/issues/101 is resolved
        if spec.type.endswith("RayProcess"):
            DI.logger.sync_resolve().warning(
                "RayProcess does not yet support event-based models. "
                "Event connectors will not be built."
            )
            event_connectors = []
        else:
            event_connectors = list(event_connector_builder.build(components).values())
        spec_connectors = [connector_builder.build(cs) for cs in spec.args.connectors]
        return sorted(
            {conn.id: conn for conn in event_connectors + spec_connectors}.values(),
            key=lambda c: c.id,
        )
