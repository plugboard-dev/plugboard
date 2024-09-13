"""Provides spec classes related to `Connector`s."""

from enum import StrEnum
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
        source: An output of a `Component` to connect from.
        target: An input of a `Component` to connect to.
        mode: The mode of the `Connector`.
    """

    source: str
    target: str
    mode: ConnectorMode = ConnectorMode.ONE_TO_ONE

    @field_validator("source", "target")
    @classmethod
    def _validate_source_target(cls, v: str) -> str:
        if v.count(".") != 1:
            raise ValueError("Source and target must be in the format 'component_name.port_name'")
        return v


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
