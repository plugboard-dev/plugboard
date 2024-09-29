"""State submodule providing functionality related to persisting process or component state."""

from plugboard.state.dict_state_backend import DictStateBackend
from plugboard.state.state_backend import StateBackend


__all__ = [
    "StateBackend",
    "DictStateBackend",
]
