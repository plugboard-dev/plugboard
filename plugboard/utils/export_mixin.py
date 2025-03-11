"""Provides `AsDictMixin` class."""

from copy import deepcopy
from functools import wraps
import inspect
import typing as _t

import msgspec
from pydantic import BaseModel


_SAVE_ARGS_INIT_KEY: str = "__save_args_init__"


@_t.runtime_checkable
class Exportable(_t.Protocol):
    """`Exportable` protocol for objects that can be exported."""

    def export(self) -> dict:
        """Returns dict representation of object for later reconstruction."""
        ...


class ExportMixin:
    """`AsDictMixin` provides functionality for converting objects to dict."""

    @staticmethod
    def _save_args_wrapper(method: _t.Callable, key: str) -> _t.Callable:
        @wraps(method)
        def _wrapper(self: _t.Any, *args: _t.Any, **kwargs: _t.Any) -> None:
            # Get positional argument names
            positional_args = [
                k
                for k, p in inspect.signature(method).parameters.items()
                if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD & (k != "self")
            ]
            saved_kwargs = ExportMixin._convert_exportable_objs(kwargs)
            saved_args = dict(zip(positional_args[: len(args)], args))
            setattr(self, key, {**getattr(self, key, {}), **saved_args, **saved_kwargs})
            method(self, *args, **kwargs)

        return _wrapper

    @staticmethod
    def _convert_exportable_objs(obj: _t.Any) -> _t.Any:
        """Recursively converts `Exportable` objects to their `export` representation."""
        if isinstance(obj, Exportable):
            return obj.export()
        elif isinstance(obj, BaseModel):
            return obj.model_dump()
        elif isinstance(obj, dict):
            return {k: ExportMixin._convert_exportable_objs(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ExportMixin._convert_exportable_objs(x) for x in obj]
        else:
            return obj

    @staticmethod
    def _dict_inject_and_copy(method: _t.Callable) -> _t.Callable:
        @wraps(method)
        def _wrapper(self: _t.Any) -> dict:
            injected_data = ExportMixin.dict(self)
            data = method(self)
            data_copy = deepcopy({**injected_data, **data})
            return data_copy

        return _wrapper

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        setattr(cls, "__init__", ExportMixin._save_args_wrapper(cls.__init__, _SAVE_ARGS_INIT_KEY))
        setattr(cls, "dict", ExportMixin._dict_inject_and_copy(cls.dict))

    def export(self) -> dict:
        """Returns dict representation of object for later reconstruction."""
        return {
            "type": _get_obj_cls_path(self),
            "args": getattr(self, _SAVE_ARGS_INIT_KEY),
        }

    def dict(self) -> dict:
        """Returns dict representation of object."""
        return {
            "__export": self.export(),
        }

    def json(self) -> bytes:
        """Returns JSON representation of object as bytes."""
        return msgspec.json.encode(self.dict())


def _get_obj_cls_path(obj: _t.Any) -> str:
    module = obj.__class__.__module__
    cls_name = obj.__class__.__name__
    if module == "builtins":
        return cls_name
    return f"{module}.{cls_name}"
