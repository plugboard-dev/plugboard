"""State submodule providing functionality related to persisting process or component state."""

from plugboard.state.dict_state_backend import DictStateBackend
from plugboard.state.state_backend import StateBackend
from plugboard.state.sqlite_state_backend import SqliteStateBackend


__all__ = [
    "StateBackend",
    "DictStateBackend",
    "SqliteStateBackend",
]
