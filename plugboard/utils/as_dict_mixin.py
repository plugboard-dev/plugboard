"""Provides `AsDictMixin` class."""

from functools import wraps
import typing as _t

import msgspec


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
            saved_kwargs = ExportMixin._convert_exportable_objs(kwargs)
            setattr(self, key, {**getattr(self, key, {}), **saved_kwargs})
            method(self, *args, **kwargs)

        return _wrapper

    @staticmethod
    def _convert_exportable_objs(kwargs: dict) -> dict:
        """Recursively converts `Exportable` objects to their `export` representation."""
        saved_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, Exportable):
                saved_kwargs[k] = v.export()
            elif isinstance(v, dict):
                saved_kwargs[k] = ExportMixin._convert_exportable_objs(v)
            elif isinstance(v, list):
                # TODO : Why does mypy complain about the following line? The below example
                #      : seems to be equivalent in terms of types and mypy doesn't complain...
                # def _convert(kwargs: dict) -> dict:
                #     saved_kwargs = {}
                #     for k, v in kwargs.items():
                #         if isinstance(v, list):
                #             v = [x for x in v]
                #             saved_kwargs[k] = v
                #     return saved_kwargs
                saved_kwargs[k] = [ExportMixin._convert_exportable_objs(x) for x in v]
            else:
                saved_kwargs[k] = v
        return saved_kwargs

    @staticmethod
    def _dict_inject_wrapper(method: _t.Callable) -> _t.Callable:
        @wraps(method)
        def _wrapper(self: _t.Any) -> dict:
            inject_data = ExportMixin.dict(self)
            data = method(self)
            return {**inject_data, **data}

        return _wrapper

    def __init_subclass__(cls, *args: _t.Any, **kwargs: _t.Any) -> None:
        cls.__init__ = ExportMixin._save_args_wrapper(cls.__init__, _SAVE_ARGS_INIT_KEY)  # type: ignore # noqa: E501,W505
        cls.dict = ExportMixin._dict_inject_wrapper(cls.dict)  # type: ignore

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
