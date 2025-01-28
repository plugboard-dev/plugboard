"""Provides path utilities."""

import contextlib
import os
import sys
from typing import Iterator


@contextlib.contextmanager
def add_sys_path(path: str | os.PathLike) -> Iterator:
    """Temporarily add `path` to `sys.path`."""
    path = os.fspath(path)
    try:
        sys.path.insert(0, path)
        yield
    finally:
        sys.path.remove(path)
