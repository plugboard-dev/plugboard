"""Utilties for working with Ray."""

from functools import wraps
import inspect
import typing as _t


T = _t.TypeVar("T")


class _ActorWrapper[T]:
    _cls: _t.Type[T]

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        self._self = self._cls(*args, **kwargs)

    def getattr(self, key: str) -> _t.Any:
        return getattr(self._self, key)

    def setattr(self, key: str, value: _t.Any) -> None:
        setattr(self._self, key, value)


def _call_with_name(func: _t.Callable) -> _t.Callable:
    @wraps(func)
    def wrapper(self: _ActorWrapper, *args: _t.Any, **kwargs: _t.Any) -> _t.Callable:
        return getattr(self._self, func.__name__)(*args, **kwargs)

    return wrapper


def _call_with_name_async(func: _t.Callable) -> _t.Callable:
    @wraps(func)
    async def wrapper(self: _ActorWrapper, *args: _t.Any, **kwargs: _t.Any) -> _t.Callable:
        return await getattr(self._self, func.__name__)(*args, **kwargs)

    return wrapper


def build_actor_wrapper(cls: type[T]) -> type[_ActorWrapper[T]]:
    """Builds an actor wrapper around a class.

    This is useful for handling classes that are modified at runtime, e.g. via wrapped methods, and
    therefore not supported by the `ray.remote` decorator.

    Args:
        cls: The class to wrap.

    Returns:
        A new class that wraps the original class and can be used as a Ray actor.
    """
    public_attrs = {name: getattr(cls, name) for name in dir(cls) if not name.startswith("_")}
    methods = {
        name: _call_with_name_async(method)
        if inspect.iscoroutinefunction(method)
        else _call_with_name(method)
        for name, method in public_attrs.items()
        if callable(method)
    }
    return type(f"{cls.__name__}Actor", (_ActorWrapper,), {**methods, "_cls": cls})
