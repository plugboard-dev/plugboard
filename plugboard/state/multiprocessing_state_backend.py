"""Provides `MultiprocessingStateBackend` class for local multiprocessing state."""

from __future__ import annotations

from multiprocessing.managers import DictProxy, SyncManager
import typing as _t

import inject

from plugboard.state.dict_state_backend import DictStateBackend


if _t.TYPE_CHECKING:
    from plugboard.process import Process


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

    async def upsert_process(self, process: Process, with_components: bool = False) -> None:
        """Upserts a process into the state."""
        # TODO : Book keeping for dynamic process components and connectors.
        process_data = process.dict()
        if with_components is False:
            process_data["components"] = self._manager.dict()
            process_data["connectors"] = self._manager.dict()
        await self._set(self._process_key(process.id), process_data)
        # TODO : Need to make this transactional.
        comp_proc_map = await self._get("_comp_proc_map")
        comp_proc_map.update({c.id: process.id for c in process.components.values()})
        await self._set("_comp_proc_map", comp_proc_map)
        # TODO : Need to make this transactional.
        conn_proc_map = await self._get("_conn_proc_map")
        conn_proc_map.update({c.id: process.id for c in process.connectors.values()})
        await self._set("_conn_proc_map", conn_proc_map)

    async def get_process(self, process_id: str) -> dict:
        """Returns a process from the state."""
        process_data = await self._get(self._process_key(process_id))
        process_data["components"] = dict(process_data["components"])
        process_data["connectors"] = dict(process_data["connectors"])
        return process_data

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        value = await super()._get(key, value)
        if isinstance(value, DictProxy):
            return dict(value)
        return value

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                if k not in _state:
                    _state[k] = self._manager.dict()
                _state = _state[k]
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = value
