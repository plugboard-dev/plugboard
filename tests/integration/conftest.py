"""Fixtures for integration tests."""

from contextlib import contextmanager
from tempfile import NamedTemporaryFile
import typing as _t

from plugboard.state import (
    DictStateBackend,
    PostgresStateBackend,
    RayStateBackend,
    SqliteStateBackend,
)


@contextmanager
def setup_DictStateBackend() -> _t.Iterator[DictStateBackend]:
    """Returns a `DictStateBackend` instance."""
    yield DictStateBackend()


@contextmanager
def setup_SqliteStateBackend() -> _t.Iterator[SqliteStateBackend]:
    """Returns a `SqliteStateBackend` instance."""
    with NamedTemporaryFile() as file:
        yield SqliteStateBackend(file.name)


@contextmanager
def setup_PostgresStateBackend() -> _t.Iterator[PostgresStateBackend]:
    """Returns a `PostgresStateBackend` instance."""
    yield PostgresStateBackend()


@contextmanager
def setup_RayStateBackend() -> _t.Iterator[RayStateBackend]:
    """Returns a `SqliteStateBackend` instance."""
    yield RayStateBackend()
