"""Provides `ProcessBuilder` to build `Process` objects."""

import typing as _t

from plugboard.component.component import Component
from plugboard.process.process import Process
from plugboard.schemas.process import ProcessSpec
from plugboard.utils.class_factory import ClassFactory


class ProcessBuilder:
    """Builds `Process` objects."""

    def __init__(self, types: list[_t.Type[Component]]):
        """Instantiates a `ProcessBuilder`.

        Args:
            types: A list of `Component` types to use in building `Process` objects.
        """
        self._component_loader: ClassFactory[Component] = ClassFactory(
            Component,  # type: ignore
            types=[t for t in types],
        )

    def build(self, spec: ProcessSpec) -> Process:
        """Build a `Process` object.

        Args:
            spec: A `ProcessSpec` object defining the `Process`.

        Returns:
            A `Process` object.
        """
        return Process(
            components=[
                self._component_loader.build(c.type, **c.args.model_dump())
                for c in spec.args.components or []
            ],
            # TODO: build connectors
            connectors=[],
            parameters=spec.args.parameters,
        )
