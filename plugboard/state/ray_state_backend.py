"""Provides `RayStateBackend` class for managing state in a Ray cluster."""

import typing as _t

from plugboard.state.dict_state_backend import DictStateBackend
from plugboard.utils import depends_on_optional


try:
    import ray
except ImportError:
    pass


class _DictionaryActor:
    """Provides a Ray actor wrapper around a dictionary state object."""

    def __init__(self) -> None:
        """Instantiates `DictActor`."""
        self._dict: dict[str, _t.Any] = {}

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        _d, _key = self._dict, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                try:
                    _d = _d[k]
                except KeyError:
                    return value
                except TypeError:
                    raise ValueError(f"Invalid key: {key}")
            # Return nested value from final key component below
            _key = key[-1]
        return _d.get(_key, value)

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        _state, _key = self._dict, key
        if isinstance(_key, tuple):
            for k in key[:-1]:  # type: str
                _state = _state.setdefault(k, {})
            _key = key[-1]  # Set nested value with final key component below
        _state[_key] = value

    def get_dict(self) -> dict[str, _t.Any]:
        """Returns the complete dictionary."""
        return self._dict

    def set_dict(self, value: dict[str, _t.Any]) -> None:
        """Sets the complete dictionary."""
        self._dict = value


class RayStateBackend(DictStateBackend):
    """`RayStateBackend` provides state persistence for Ray cluster runs."""

    @depends_on_optional("ray")
    def __init__(
        self, *args: _t.Any, actor_options: _t.Optional[dict] = None, **kwargs: _t.Any
    ) -> None:
        """Instantiates `RayStateBackend`.

        Args:
            *args: Additional positional arguments to pass to the underlying `StateBackend`.
            actor_options: Optional; Options to pass to the Ray actor. Defaults to {"num_cpus": 0}.
            **kwargs: Additional keyword arguments to pass to the the underlying `StateBackend`.
        """
        super().__init__(*args, **kwargs)
        default_options = {"num_cpus": 0}
        actor_options = actor_options or {}
        actor_options = {**default_options, **actor_options}
        self._actor = ray.remote(**actor_options)(_DictionaryActor).remote()

    @property
    def _state(self) -> dict[str, _t.Any]:
        """State dictionary."""
        return ray.get(self._actor.get_dict.remote())  # type: ignore

    @_state.setter
    def _state(self, value: dict[str, _t.Any]) -> None:
        """Set state dictionary."""
        ray.get(self._actor.set_dict.remote(value))  # type: ignore

    async def _get(self, key: str | tuple[str, ...], value: _t.Optional[_t.Any] = None) -> _t.Any:
        return await self._actor._get.remote(key, value)  # type: ignore

    async def _set(self, key: str | tuple[str, ...], value: _t.Any) -> None:  # noqa: A003
        await self._actor._set.remote(key, value)  # type: ignore
