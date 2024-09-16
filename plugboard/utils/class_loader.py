"""Provides `ClassLoader` utility to load Plugboard classes."""

from pydoc import locate
import typing as _t


T = _t.TypeVar("T")


class ClassLoader(_t.Generic[T]):
    """Utility to build Plugboard objects."""

    def __init__(self, class_type: _t.Type[T], types: list[_t.Type[T]]):
        """Instantiates a `ClassLoader`.

        Args:
            class_type: The type of class to load.
            types: A list of known types available to use.
        """
        self._class_type = class_type
        self._types = {t.__name__: t for t in types}

    def load(self, type_name: str) -> _t.Type[T]:
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

    def build(self, type_name: str, *args: _t.Any, **kwargs: _t.Any) -> T:
        """Build an instance of a class by name.

        Args:
            type_name: The name of the class to build.
            *args: Positional arguments to pass to the class constructor.
            **kwargs: Keyword arguments to pass to the class constructor.

        Returns:
            An instance of the class.
        """
        return self.load(type_name)(*args, **kwargs)
