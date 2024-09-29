"""Provides `DictStateBackend` class for single process state management."""

import typing as _t

from plugboard.state.state_backend import StateBackend


class DictStateBackend(StateBackend):
    """`DictStateBackend` provides state persistence for single process runs."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Initialises `DictStateBackend`."""
        self._state: dict = {}
        super().__init__(*args, **kwargs)

    async def _get(self, key: str | tuple[str], value: _t.Optional[_t.Any] = None) -> _t.Any:
        _state, _key = self._state, key
        if isinstance(key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.get(k, {})
                if k not in _state:
                    break
            _key = key[-1]
        return _state.get(_key, value)

    async def _set(self, key: str | tuple[str], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state, key
        if isinstance(key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, {})
            _key = key[-1]
        _state[_key] = value
