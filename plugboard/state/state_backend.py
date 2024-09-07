"""Provides `StateBackend` base class for managing process state."""

from abc import ABC

from plugboard.utils import AsDictMixin


class StateBackend(ABC, AsDictMixin):
    """`StateBackend` defines an interface for managing process state."""

    pass
