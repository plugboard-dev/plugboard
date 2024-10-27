"""Provides `ConnectorSpec` container class."""

from __future__ import annotations

import typing as _t

from plugboard.connector.channel import Channel
from plugboard.schemas.connector import ConnectorSpec
from plugboard.utils import ExportMixin


class Connector(ExportMixin):
    """`Connector` contains a `Channel` connecting two components."""

    def __init__(self, spec: ConnectorSpec, channel: Channel) -> None:
        self.spec: ConnectorSpec = spec
        self.channel: Channel = channel

    @property
    def id(self) -> str:
        """Unique ID for `Connector`."""
        return self.spec.id

    def export(self) -> dict:  # noqa: D102
        return self.spec.model_dump()

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "id": self.id,
            "spec": self.spec.model_dump(),
        }
