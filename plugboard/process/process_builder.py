"""Provides `ProcessBuilder` to build `Process` objects."""

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
        return Process(
            # TODO: load components
            components=[],
            # TODO: build connectors
            connectors=[],
            parameters=spec.args.parameters,
        )
