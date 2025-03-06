"""Utilties for working with Ray."""

from functools import wraps
import inspect
import typing as _t


try:
    import ray
except ImportError:
    pass

T = _t.TypeVar("T")


class _ActorWrapper[T]:
    _cls: _t.Type[T]

    def __init__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
        self._self = self._cls(*args, **kwargs)

    def getattr(self, key: str) -> _t.Any:
        return getattr(self._self, key, None)

    def setattr(self, key: str, value: _t.Any) -> None:
        setattr(self._self, key, value)


def _call_with_name(func: _t.Callable, path: tuple[str, ...]) -> _t.Callable:
    @wraps(func)
    def wrapper(self: _ActorWrapper, *args: _t.Any, **kwargs: _t.Any) -> _t.Callable:
        obj = self._self
        for name in path:
            obj = getattr(obj, name)
        return getattr(obj, func.__name__)(*args, **kwargs)

    return wrapper


def _call_with_name_async(func: _t.Callable, path: tuple[str, ...]) -> _t.Callable:
    @wraps(func)
    async def wrapper(self: _ActorWrapper, *args: _t.Any, **kwargs: _t.Any) -> _t.Callable:
        obj = self._self
        for name in path:
            obj = getattr(obj, name)
        return await getattr(obj, func.__name__)(*args, **kwargs)

    return wrapper


def _wrap_methods(obj: object, path: tuple[str, ...]) -> _t.Iterator[tuple[str, _t.Callable]]:
    """Recursively wraps all public methods on a class."""
    public_attrs = {name: getattr(obj, name) for name in dir(obj) if not name.startswith("_")}
    prefix = "_".join(path) + "_" if path else ""
    for name, attr in public_attrs.items():
        if callable(attr):
            if inspect.iscoroutinefunction(attr):
                yield f"{prefix}{name}", _call_with_name_async(attr, path)
            else:
                yield f"{prefix}{name}", _call_with_name(attr, path)
        elif not attr.__class__.__module__ == "builtins":
            yield from _wrap_methods(attr, (*path, name))


def build_actor_wrapper(cls: type[T]) -> type[_ActorWrapper[T]]:
    """Builds an actor wrapper around a class.

    This is useful for handling classes that are modified at runtime, e.g. via wrapped methods, and
    therefore not supported by the `ray.remote` decorator.

    The wrapper methods will have the same name as the original methods, but where nested in class
    attributes the method names will be prefixed accordingly. The wrapper also provides a `getattr`
    and `setattr` method to access the wrapped object's properties.

    Args:
        cls: The class to wrap.

    Returns:
        A new class that wraps the original class and can be used as a Ray actor.
    """
    methods = dict(_wrap_methods(cls, tuple()))
    return type(f"{cls.__name__}Actor", (_ActorWrapper,), {**methods, "_cls": cls})


def is_on_ray_worker() -> bool:
    """Returns `True` if called from a Ray worker."""
    try:
        if ray.is_initialized():
            ctx = ray.get_runtime_context()
            if ctx.worker.mode == ray.WORKER_MODE:
                return True
    except NameError:
        pass
    return False
