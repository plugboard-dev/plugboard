"""Provides spec classes related to `Connector`s."""

from enum import StrEnum
import re
import typing as _t

from pydantic import BaseModel, field_validator


class ConnectorMode(StrEnum):
    """Defines the mode of a connector.

    Attributes:
        ONE_TO_ONE: Specifies a one-to-one connection.
        ONE_TO_MANY: Specifies a one-to-many connection.
        MANY_TO_ONE: Specifies a many-to-one connection.
        MANY_TO_MANY: Specifies a many-to-many connection.
    """

    ONE_TO_ONE = "one-to-one"
    ONE_TO_MANY = "one-to-many"
    MANY_TO_ONE = "many-to-one"
    MANY_TO_MANY = "many-to-many"


class ComponentSocket(BaseModel):
    """`ComponentSocket` defines a connection point for a component.

    Attributes:
        component: The name of the component.
        field: The name of the I/O field on the component.
    """

    _PATTERN: _t.ClassVar[re.Pattern] = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_-]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
    )

    component: str
    field: str

    @classmethod
    def from_ref(cls, ref: str) -> _t.Self:
        """Creates a `ComponentSocket` from a reference string."""
        match = cls._PATTERN.match(ref)
        if not match:
            raise ValueError(f"Reference must be of the form 'component.field', got {ref}")
        component, field = match.groups()
        return cls(component=component, field=field)

    @property
    def id(self) -> str:
        """Unique ID for `ComponentSocket`."""
        return f"{self.component}.{self.field}"

    def __str__(self) -> str:
        return self.id


class ConnectorSpec(BaseModel):
    """`ConnectorSpec` defines a connection between two components.

    Attributes:
        source: The source component socket.
        target: The target component socket.
        mode: The mode of the connector.
    """

    source: ComponentSocket
    target: ComponentSocket
    mode: ConnectorMode = ConnectorMode.ONE_TO_ONE

    @field_validator("source", "target", mode="before")
    @classmethod
    def _validate_source_target(cls, v: ComponentSocket | str) -> ComponentSocket:
        if not isinstance(v, ComponentSocket):
            return ComponentSocket.from_ref(v)
        return v

    @property
    def id(self) -> str:
        """Unique ID for `ConnectorSpec`."""
        return f"{self.source.id}..{self.target.id}"

    def __str__(self) -> str:
        return self.id


class ChannelBuilderArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`Channel`][plugboard.connector.Channel] constructor arguments.

    Attributes:
        parameters: Parameters for the `Channel`.
    """

    parameters: dict = {}


class ChannelBuilderSpec(BaseModel):
    """Specification of a `ChannelBuilder`.

    Attributes:
        type: The type of the `ChannelBuilder`.
        args: Optional; The arguments for the `ChannelBuilder`.
    """

    type: str
    args: ChannelBuilderArgsSpec = ChannelBuilderArgsSpec()
