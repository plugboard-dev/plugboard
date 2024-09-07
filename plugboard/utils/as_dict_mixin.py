"""Provides `AsDictMixin` class."""

from functools import wraps
import typing as _t


_SAVE_ARGS_INIT_KEY: str = "__save_args_init__"


class AsDictMixin:
    """`AsDictMixin` provides functionality for converting objects to dict."""

    @staticmethod
    def _save_args_wrapper(method: _t.Callable, key: str) -> _t.Callable:
        @wraps(method)
        def _wrapper(self: _t.Any, *args: _t.Any, **kwargs: _t.Any) -> None:
            setattr(self, key, {**getattr(self, key, {}), **kwargs})
            method(self, *args, **kwargs)

        return _wrapper

    @staticmethod
    def _dict_inject_wrapper(method: _t.Callable) -> _t.Callable:
        @wraps(method)
        def _wrapper(self: _t.Any) -> None:
            inject_data = AsDictMixin.dict(self)
            data = method(self)
            return {**inject_data, **data}

        return _wrapper

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        cls.__init__ = AsDictMixin._save_args_wrapper(cls.__init__, _SAVE_ARGS_INIT_KEY)
        cls.dict = AsDictMixin._dict_inject_wrapper(cls.dict)

    def dict(self) -> dict:
        """Returns dict representation of object."""
        return {
            "__export": {
                "type": _get_obj_cls_path(self),
                "args": getattr(self, _SAVE_ARGS_INIT_KEY),
            }
        }


def _get_obj_cls_path(obj: _t.Any):
    module = obj.__class__.__module__
    cls_name = obj.__class__.__name__
    if module == "builtins":
        return cls_name
    return f"{module}.{cls_name}"
