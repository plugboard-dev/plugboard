"""Provides `ConnectorSpec` container class."""

from __future__ import annotations

import re
import typing as _t

from pydantic import BaseModel
from pydantic.fields import ClassVar

from plugboard.connector.channel import Channel
from plugboard.schemas.connector import ConnectorMode
from plugboard.utils import AsDictMixin


class Connector(AsDictMixin):
    """`Connector` contains a `Channel` connecting two components."""

    def __init__(self, spec: ConnectorSpec, channel: Channel) -> None:
        self.spec: ConnectorSpec = spec
        self.channel: Channel = channel

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "spec": self.spec.dict(),
        }


class ConnectorSpec:
    """`ConnectorSpec` defines a connection between two components."""

    def __init__(
        self, source: str, target: str, mode: ConnectorMode = ConnectorMode.ONE_TO_ONE
    ) -> None:
        self.source = ComponentSocket.from_ref(source)
        self.target = ComponentSocket.from_ref(target)
        self.mode = mode

    @property
    def id(self) -> str:  # noqa: D102
        return f"{self.source.id}..{self.target.id}"

    def __str__(self) -> str:
        return self.id

    def dict(self) -> dict[str, _t.Any]:  # noqa: D102
        return {
            "source": str(self.source),
            "target": str(self.target),
            "mode": self.mode,
        }


class ComponentSocket(BaseModel):
    """`ComponentSocket` defines a connection point for a component."""

    _PATTERN: ClassVar[re.Pattern] = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
    )

    component: str
    field: str

    @classmethod
    def from_ref(cls, ref: str) -> ComponentSocket:
        """Creates a `ComponentSocket` from a reference string."""
        match = cls._PATTERN.match(ref)
        if not match:
            raise ValueError(f"Reference must be of the form 'component.field', got {ref}")
        component, field = match.groups()
        return cls(component=component, field=field)

    @property
    def id(self) -> str:  # noqa: D102
        return f"{self.component}.{self.field}"

    def __str__(self) -> str:
        return self.id
