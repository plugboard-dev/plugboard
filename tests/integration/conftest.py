"""Fixtures for integration tests."""

from contextlib import contextmanager
from tempfile import NamedTemporaryFile
import typing as _t

from plugboard.state import DictStateBackend, MultiprocessingStateBackend, SqliteStateBackend


@contextmanager
def setup_DictStateBackend() -> _t.Iterator[DictStateBackend]:
    """Returns a `DictStateBackend` instance."""
    yield DictStateBackend()


@contextmanager
def setup_MultiprocessingStateBackend() -> _t.Iterator[MultiprocessingStateBackend]:
    """Returns a `MultiprocessingStateBackend` instance."""
    yield MultiprocessingStateBackend()


@contextmanager
def setup_SqliteStateBackend() -> _t.Iterator[SqliteStateBackend]:
    """Returns a `SqliteStateBackend` instance."""
    with NamedTemporaryFile() as file:
        yield SqliteStateBackend(file.name)
