"""Provides definitions for entity names and id syntax."""

from enum import StrEnum
import typing as _t


_ENTITY_SEP: _t.Final[str] = "_"
_ENTITY_ID_MIN_CHARS: _t.Final[int] = 8
_ENTITY_ID_SUFFIX_REGEX: _t.Final[str] = (
    _ENTITY_SEP + rf"(?P<id>[a-zA-Z0-9]{{{_ENTITY_ID_MIN_CHARS},}})$"
)


class Entity(StrEnum):
    """Entity names."""

    Job = "Job"

    @property
    def id_prefix(self) -> str:
        """Returns prefix for generating unique entity ids."""
        return str(self) + _ENTITY_SEP

    @property
    def id_regex(self) -> str:
        """Returns regex for validating entity ids."""
        return rf"^(?P<entity>{self})" + _ENTITY_ID_SUFFIX_REGEX


ENTITY_ID_REGEX = rf"^(?P<entity>{'|'.join([e.name for e in Entity])})" + _ENTITY_ID_SUFFIX_REGEX
