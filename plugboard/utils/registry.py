"""Provides a generic registry for Plugboard objects."""

from abc import ABC
import typing as _t


T = _t.TypeVar("T")


class ClassRegistry(ABC, _t.Generic[T]):
    """A registry of Plugboard classes."""

    classes: _t.Dict[_t.Hashable, type[T]]

    @classmethod
    def __init_subclass__(cls) -> None:
        cls.classes = {}

    @classmethod
    def add(cls, plugboard_class: type[T], key: _t.Optional[_t.Hashable] = None) -> None:
        """Add a class to the registry.

        Args:
            plugboard_class: The class to register.
            key: Optional; The key to register the class under.
        """
        key = key or f"{plugboard_class.__module__}.{plugboard_class.__qualname__}"
        cls.classes[key] = plugboard_class

    @classmethod
    def get(cls, plugboard_class: _t.Hashable) -> type[T]:
        """Returns a class from the registry.

        Args:
            plugboard_class: The key corresponding to the required class.

        Returns:
            The class.
        """
        return cls.classes[plugboard_class]

    @classmethod
    def build(cls, plugboard_class: _t.Hashable, *args: _t.Any, **kwargs: _t.Any) -> T:
        """Builds a Plugboard object.

        Args:
            plugboard_class: The key corresponding to the required class.
            *args: Positional arguments to pass to the class constructor.
            **kwargs: Keyword arguments to pass to the class constructor.

        Returns:
            An object of the required class.
        """
        return cls.classes[plugboard_class](*args, **kwargs)
