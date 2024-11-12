"""Provides `MultiprocessingStateBackend` class for local multiprocessing state."""

from __future__ import annotations

from collections.abc import MutableMapping
import typing as _t

import inject
from multiprocess.managers import DictProxy, SyncManager

from plugboard.state.dict_state_backend import DictStateBackend


def _flatten_dict(
    d: dict[str, _t.Any], parent_key: _t.Optional[tuple[str, ...]] = None
) -> dict[tuple[str, ...], _t.Any]:
    """Flattens nested dictionaries."""
    items: list[tuple[tuple[str, ...], _t.Any]] = []
    for k, v in d.items():
        new_key = parent_key + (k,) if parent_key else (k,)
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    # Handle case of empty dict
    if not items and parent_key:
        items.append((parent_key, {}))
    return dict(items)


def _unflatten_dict(d: MutableMapping[tuple[str, ...], _t.Any]) -> dict[str, _t.Any]:
    """Converts flattened dictionaries back to a nested form."""
    result: dict[str, _t.Any] = {}
    for k, v in d.items():
        current = result
        for key in k[:-1]:
            current = current.setdefault(key, {})
        current[k[-1]] = v
    return result


class MultiprocessingStateBackend(DictStateBackend):
    """`MultiprocessingStateBackend` provides state persistence for multiprocess runs."""

    @inject.params(manager=SyncManager)
    def __init__(self, manager: SyncManager, *args: _t.Any, **kwargs: _t.Any) -> None:  # noqa: D417
        """Instantiates `MultiprocessingStateBackend`.

        Args:
            manager: A multiprocessing manager.
        """
        super().__init__(*args, **kwargs)
        # Store flattened key-value pairs to avoid needing nested managed dictionaries
        self._state_mgr: DictProxy[tuple[str, ...], _t.Any] = manager.dict()  # type: ignore

    @property
    def _state(self) -> dict[str, _t.Any]:
        """State dictionary."""
        return _unflatten_dict(self._state_mgr)

    @_state.setter
    def _state(self, value: dict[str, _t.Any]) -> None:
        """Set state dictionary."""
        self._state_mgr.update(_flatten_dict(value))

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        if isinstance(key, str):
            key = (key,)
        if key in self._state_mgr:
            return self._state_mgr[key]

        # Fetch nested dictionary if any
        items = {k[len(key) :]: v for k, v in self._state_mgr.items() if k[: len(key)] == key}
        if not items:
            return value
        return _unflatten_dict(items)

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        if isinstance(key, str):
            key = (key,)
        if isinstance(value, dict):
            update = _flatten_dict(value, key)
        else:
            update = {key: value}
        self._state_mgr.update(update)
        # Prune overwritten keys from the state
        for k in update.keys():
            for n in range(1, len(k)):
                self._state_mgr.pop(k[:n], None)
