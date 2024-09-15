"""Provides `ProcessBuilder` to build `Process` objects."""

from pydoc import locate
import typing as _t

from plugboard.component.component import Component
from plugboard.process.process import Process
from plugboard.schemas.process import ProcessSpec


class ProcessBuilder:
    """Builds `Process` objects."""

    def __init__(self, types: list[_t.Type[Component]]):
        """Instantiates a `ProcessBuilder`.

        Args:
            types: A list of `Component` types to use in building `Process` objects.
        """
        self._component_types = {ct.__name__: ct for ct in types}

    def _load_type(self, type_name: str) -> _t.Type[Component]:
        try:
            return self._component_types[type_name]
        except KeyError:
            ct = locate(type_name)
            if ct is None or not issubclass(ct, Component):
                raise ValueError(f"Component type {type_name} not found.")
            self._component_types[type_name] = ct
            return ct

    def build(self, spec: ProcessSpec) -> Process:
        """Build a `Process` object.

        Args:
            spec: A `ProcessSpec` object defining the `Process`.

        Returns:
            A `Process` object.
        """
        return Process(
            components=[self._load_type(c.type)(**c.args) for c in spec.args.components],
            # TODO: build connectors
            connectors=[],
            parameters=spec.args.parameters,
        )
