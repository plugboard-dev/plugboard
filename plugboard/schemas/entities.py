"""Provides definitions for entity names and id syntax."""

from enum import StrEnum
import typing as _t


_ENTITY_SEP: _t.Final[str] = "_"


class Entity(StrEnum):
    """Entity names."""

    Job: str = "Job"

    def id_prefix(self) -> str:
        """Returns prefix for generating unique entity ids."""
        return str(self) + _ENTITY_SEP
