"""Provides `ConnectorBuilder` to build `Connector` objects."""

import typing as _t

from plugboard.connector.connector import Connector
from plugboard.schemas.connector import ConnectorSpec


class ConnectorBuilder:
    """`ConnectorBuilder` facilitates building `Connector`s with a preset configuration."""

    def __init__(self, connector_cls: type[Connector], *args: _t.Any, **kwargs: _t.Any) -> None:
        self._connector_cls: type[Connector] = connector_cls
        self._args: _t.Any = args
        self._kwargs: _t.Any = kwargs

    def build(self, spec: ConnectorSpec) -> Connector:
        """Builds a `Connector` object."""
        return self._connector_cls(spec, *self._args, **self._kwargs)
