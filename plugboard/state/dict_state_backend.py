"""Provides `DictStateBackend` class for single process state management."""

import typing as _t

from that_depends import Provide, inject

from plugboard.exceptions import NotFoundError
from plugboard.state.state_backend import StateBackend
from plugboard.utils import DI


class DictStateBackend(StateBackend):
    """`DictStateBackend` provides state persistence for single process runs."""

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        """Instantiates `DictStateBackend`."""
        super().__init__(*args, **kwargs)
        self._state_dict: dict[str, _t.Any] = {}

    @property
    def _state(self) -> dict[str, _t.Any]:
        """State dictionary."""
        return self._state_dict

    @_state.setter
    def _state(self, value: dict[str, _t.Any]) -> None:
        """Set state dictionary."""
        self._state_dict.update(value)

    @inject
    async def _initialise_data(
        self, job_id: str = Provide[DI.job_id], metadata: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        await super()._initialise_data(job_id=job_id, metadata=metadata, **kwargs)
        comp_proc_map: dict = dict()
        await self._set("_comp_proc_map", comp_proc_map)
        conn_proc_map: dict = dict()
        await self._set("_conn_proc_map", conn_proc_map)

    async def _get_job(self, job_id: str) -> dict:
        raise NotFoundError("Cannot reuse job ID for non-persistent backend.")

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        _state, _key = self._state_dict, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                try:
                    _state = _state[k]
                except KeyError:
                    return value
                except TypeError:
                    raise ValueError(f"Invalid key: {key}")
            _key = key[-1]  # Return nested value from final key component below
        return _state.get(_key, value)

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._state_dict, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, {})
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = value
