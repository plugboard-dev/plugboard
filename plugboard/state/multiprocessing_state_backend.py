"""Provides `MultiprocessingStateBackend` class for local multiprocessing state."""

from multiprocessing import DictProxy, Manager
import typing as _t

from plugboard.state.dict_state_backend import DictStateBackend


class MultiprocessingStateBackend(DictStateBackend):
    """`MultiprocessingStateBackend` provides state persistence for single process runs."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Instantiates `MultiprocessingStateBackend`."""
        super().__init__(*args, **kwargs)
        self._manager = Manager()
        self._state: DictProxy[str, _t.Any] = self._manager.dict()

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, self._manager.dict())
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = value
