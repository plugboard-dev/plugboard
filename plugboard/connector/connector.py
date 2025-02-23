"""Provides `ConnectorSpec` container class."""

from __future__ import annotations

from abc import ABC, abstractmethod
import typing as _t

from plugboard.connector.channel import Channel
from plugboard.schemas.connector import ConnectorSpec
from plugboard.utils import ExportMixin


class Connector(ABC, ExportMixin):
    """`Connector` provides `Channel`s for communication between a specified source and target."""

    def __init__(self, spec: ConnectorSpec, *args: _t.Any, **kwargs: _t.Any) -> None:
        self.spec: ConnectorSpec = spec

    @abstractmethod
    async def connect_send(self) -> Channel:
        """Returns a `Channel` for sending messages."""
        pass

    @abstractmethod
    async def connect_recv(self) -> Channel:
        """Returns a `Channel` for receiving messages."""
        pass

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
