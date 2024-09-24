"""Provides `ProcessBuilder` to build `Process` objects."""

from pydoc import locate
import typing as _t

from plugboard.component.component import Component, ComponentRegistry
from plugboard.connector.channel_builder import ChannelBuilder
from plugboard.connector.connector import Connector
from plugboard.process.process import Process
from plugboard.schemas.process import ProcessSpec


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
        for c in spec.args.components or []:
            component_class: _t.Optional[_t.Any] = locate(c.type)
            if not component_class or not issubclass(component_class, Component):
                raise ValueError(f"Component class {c.type} not found.")
        channel_builder_class: _t.Optional[_t.Any] = locate(spec.channel_builder.type)
        if not channel_builder_class or not issubclass(channel_builder_class, ChannelBuilder):
            raise ValueError(f"ChannelBuilder class {spec.channel_builder.type} not found")
        channel_builder = channel_builder_class()

        return Process(
            components=[
                ComponentRegistry.build(c.type, **dict(c.args)) for c in spec.args.components
            ],
            connectors=[
                Connector(cs, channel_builder.build(**dict(spec.channel_builder.args)))
                for cs in spec.args.connectors
            ],
            parameters=spec.args.parameters,
        )
