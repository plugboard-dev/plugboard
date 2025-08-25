"""Provides spec classes related to `Connector`s."""

from collections.abc import Container
from enum import StrEnum
import re
import typing as _t

from pydantic import Field, field_validator

from plugboard.schemas._common import PlugboardBaseModel


DEFAULT_CONNECTOR_CLS_PATH: str = "plugboard.connector.AsyncioConnector"


class ConnectorMode(StrEnum):
    """Defines the mode of a connector.

    Attributes:
        PIPELINE: one-in-one-out task queue.
        PUBSUB: one-to-many event distribution.
    """

    PIPELINE = "pipeline"
    PUBSUB = "pubsub"


class ConnectorSocket(PlugboardBaseModel):
    """`ConnectorSocket` defines a source or target connection point on a `Connector`.

    There are two typical types of connections in use: those between attributes of components;
    and those connecting components with events which they either emit or consume. When connecting
    two component attributes together, the `entity` is the name of the component, and the
    `descriptor` is the name of the attribute. When connecting components with events, the `entity`
    is the name of the event, and the `descriptor` is either "publishers" or "subscribers" as
    appropriate.

    Attributes:
        entity: The name of the entity.
        descriptor: The name of the descriptor on the entity.
    """

    _PATTERN: _t.ClassVar[re.Pattern] = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_\-]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
    )

    entity: str
    descriptor: str

    @classmethod
    def from_ref(cls, ref: str) -> _t.Self:
        """Creates a `ConnectorSocket` from a reference string."""
        match = cls._PATTERN.match(ref)
        if not match:
            raise ValueError(f"Reference must be of the form 'entity.descriptor', got {ref}")
        entity, descriptor = match.groups()
        return cls(entity=entity, descriptor=descriptor)

    @property
    def id(self) -> str:
        """Unique ID for `ConnectorSocket`."""
        return f"{self.entity}.{self.descriptor}"

    def __str__(self) -> str:
        return self.id

    def connects_to(self, entities: Container[str]) -> bool:
        """Returns `True` if the `ConnectorSocket` connects to any of the named entities."""
        return self.entity in entities


class ConnectorSpec(PlugboardBaseModel):
    """`ConnectorSpec` defines a connection between two entities.

    Attributes:
        source: The source endpoint.
        target: The target endpoint.
        mode: The mode of the connector.
    """

    source: ConnectorSocket
    target: ConnectorSocket
    mode: ConnectorMode = Field(default=ConnectorMode.PIPELINE, validate_default=True)

    @field_validator("source", "target", mode="before")
    @classmethod
    def _validate_source_target(cls, v: ConnectorSocket | dict | str) -> ConnectorSocket | dict:
        if isinstance(v, str):
            return ConnectorSocket.from_ref(v)
        return v

    @property
    def id(self) -> str:
        """Unique ID for `ConnectorSpec`."""
        return f"{self.source.id}..{self.target.id}"

    def __str__(self) -> str:
        return self.id


class ConnectorBuilderArgsDict(_t.TypedDict):
    """`TypedDict` of the [`Connector`][plugboard.connector.Connector] constructor arguments."""

    parameters: dict[str, _t.Any]


class ConnectorBuilderArgsSpec(PlugboardBaseModel, extra="allow"):
    """Specification of the [`Connector`][plugboard.connector.Connector] constructor arguments.

    Attributes:
        parameters: Parameters for the `Connector`.
    """

    parameters: dict[str, _t.Any] = {}


class ConnectorBuilderSpec(PlugboardBaseModel):
    """Specification of a `ConnectorBuilder`.

    Attributes:
        type: The type of the `ConnectorBuilder`.
        args: Optional; The arguments for the `ConnectorBuilder`.
    """

    type: str = DEFAULT_CONNECTOR_CLS_PATH
    args: ConnectorBuilderArgsSpec = ConnectorBuilderArgsSpec()
