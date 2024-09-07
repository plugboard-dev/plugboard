"""Provides `StateBackendSpec` class."""

from pydantic import BaseModel


class StateBackendSpec(BaseModel):
    """Specification of a Plugboard `StateBackend`."""

    type: str
    parameters: dict
