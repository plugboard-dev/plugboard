"""Provides spec classes related to `Connector`s."""

from enum import StrEnum
import typing as _t

from pydantic import BaseModel


class ConnectorMode(StrEnum):
    """Defines the mode of a connector."""

    ONE_TO_ONE = "one-to-one"
    ONE_TO_MANY = "one-to-many"
    MANY_TO_ONE = "many-to-one"
    MANY_TO_MANY = "many-to-many"


class ConnectorSpec(BaseModel):
    """Specification of a Plugboard `Connector`."""

    source: str
    target: str
    mode: ConnectorMode = ConnectorMode.ONE_TO_ONE

    @property
    def id(self) -> str:  # noqa: D102
        return f"{self.source.id}..{self.target.id}"


class ConnectorBuilderArgsSpec(BaseModel, extra="allow"):
    """Specification of the `Connector` constructor arguments."""

    parameters: _t.Optional[dict] = None


class ConnectorBuilderSpec(BaseModel):
    """Specification of a Plugboard `ConnectorBuilder`."""

    type: str
    args: ConnectorBuilderArgsSpec
