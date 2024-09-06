"""Provides `ConnectorSpec` class."""

from pydantic import BaseModel


class ConnectorSpec(BaseModel):
    """Specification of a Plugboard `Connector`."""

    source: str
    target: str
    # TODO: change to enum
    mode: str = "ONE_TO_ONE"
