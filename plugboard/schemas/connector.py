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


class ConnectorSpec(BaseModel):
    """Specification of a Plugboard [`Connector`][plugboard.connector.Connector].

    Attributes:
        source: An output from a `Component` in the form `component_name.field_name`.
        target: An input to a `Component`  in the form `component_name.field_name`.
        mode: The mode of the `Connector`.
    """

    source: str
    target: str
    mode: ConnectorMode = ConnectorMode.ONE_TO_ONE

    @field_validator("source", "target")
    @classmethod
    def _validate_source_target(cls, v: str) -> str:
        if v.count(".") != 1:
            raise ValueError("Source and target must be in the format 'component_name.field_name'")
        return v


class ComponentSocket(BaseModel):
    """`ComponentSocket` defines a connection point for a component.

    Attributes:
        component: The name of the component.
        field: The name of the I/O field on the component.
    """

    _PATTERN: _t.ClassVar[re.Pattern] = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
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
    def id(self) -> str:  # noqa: D102
        return f"{self.component}.{self.field}"

    def __str__(self) -> str:
        return self.id


class ConnectorBuilderArgsSpec(BaseModel, extra="allow"):
    """Specification of the [`Connector`][plugboard.connector.Connector] constructor arguments.

    Attributes:
        parameters: Optional; Parameters for the `Connector`.
    """

    parameters: _t.Optional[dict] = None


class ConnectorBuilderSpec(BaseModel):
    """Specification of a `ConnectorBuilder`.

    Attributes:
        type: The type of the `ConnectorBuilder`.
        args: The arguments for the `ConnectorBuilder`.
    """

    type: str
    args: ConnectorBuilderArgsSpec
