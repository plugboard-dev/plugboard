"""Provides `MultiprocessingStateBackend` class for local multiprocessing state."""

from __future__ import annotations

from multiprocessing.managers import DictProxy, SyncManager
import typing as _t

import inject

from plugboard.state.dict_state_backend import DictStateBackend


class MultiprocessingStateBackend(DictStateBackend):
    """`MultiprocessingStateBackend` provides state persistence for single process runs."""

    @inject.params(manager=SyncManager)
    def __init__(self, manager: SyncManager, *args: _t.Any, **kwargs: _t.Any) -> None:  # noqa: D417
        """Instantiates `MultiprocessingStateBackend`.

        Args:
            manager: A multiprocessing manager.
        """
        super().__init__(*args, **kwargs)
        self._manager = manager
        self._state: DictProxy[str, _t.Any] = self._manager.dict()

    @classmethod
    def _convert_value(cls, value: _t.Any) -> _t.Any:
        """Recursively convert DictProxy objects to dictionaries."""
        if isinstance(value, DictProxy) or isinstance(value, dict):
            return {k: cls._convert_value(v) for k, v in value.items()}
        return value

    def _prepare_value(self, value: _t.Any) -> _t.Any:
        """Recursively convert dictionaries to DictProxy objects."""
        if isinstance(value, dict):
            return self._manager.dict({k: self._prepare_value(v) for k, v in value.items()})
        return value

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        return self._convert_value(await super()._get(key, value))

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, self._manager.dict())
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = self._prepare_value(value)
