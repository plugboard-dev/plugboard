"""Provides `MultiprocessingStateBackend` class for local multiprocessing state."""

from multiprocessing import DictProxy
from multiprocessing.managers import SyncManager
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

    async def _initialise_data(
        self, job_id: _t.Optional[str] = None, metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        await super()._initialise_data(job_id, metadata, **kwargs)
        comp_proc_map: dict = self._manager.dict()
        await self._set("_comp_proc_map", comp_proc_map)
        conn_proc_map: dict = self._manager.dict()
        await self._set("_conn_proc_map", conn_proc_map)

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, self._manager.dict())
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = value
