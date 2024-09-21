"""Provides `ClassFactory` utility to build Plugboard objects."""

from pydoc import locate
import typing as _t


T = _t.TypeVar("T")


class ClassLoader(_t.Generic[T]):
    """Loads Plugboard classes."""

    def __init__(self, class_type: type[T], types: _t.Optional[list[type[T]]] = None):
        """Instantiates a `ClassLoader`.

        Args:
            class_type: The type of class to load.
            types: A list of known types available to use.
        """
        self._class_type = class_type
        self._types = {t.__name__: t for t in types} if types else {}

    def load(self, type_name: str) -> type[T]:
        """Load a class by name.

        Args:
            type_name: The name of the class to load.

        Returns:
            The class.
        """
        try:
            return self._types[type_name]
        except KeyError:
            t: _t.Optional[_t.Any] = locate(type_name)
            if t is None or not issubclass(t, self._class_type):
                raise ValueError(f"Type {type_name} not found.")
            self._types[type_name] = t
            return t
