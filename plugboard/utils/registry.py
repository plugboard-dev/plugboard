"""Provides a generic registry for Plugboard objects."""

from abc import ABC
import typing as _t


T = _t.TypeVar("T")


class Registry(ABC, _t.Generic[T]):
    """A registry of Plugboard classes."""

    classes: _t.Dict[_t.Hashable, type[T]]

    @classmethod
    def __init_subclass__(cls) -> None:
        cls.classes = {}

    @classmethod
    def register(cls, plugboard_class: type[T], key: _t.Optional[_t.Hashable] = None) -> None:
        """Register a class.

        Args:
            plugboard_class: The class to register.
            key: Optional; The key to register the class under.
        """
        key = key or f"{plugboard_class.__module__}.{plugboard_class.__qualname__}"
        cls.classes[key] = plugboard_class

    @classmethod
    def get_class(cls, plugboard_class: _t.Hashable) -> type[T]:
        """Returns a class from the registry.

        Args:
            plugboard_class: The key corresponding to the required class.

        Returns:
            The class.
        """
        return cls.classes[plugboard_class]

    @classmethod
    def build_object(cls, plugboard_class: _t.Hashable, *args: _t.Any, **kwargs: _t.Any) -> T:
        """Builds a Plugboard object.

        Args:
            plugboard_class: The key corresponding to the required class.
            *args: Positional arguments to pass to the class constructor.
            **kwargs: Keyword arguments to pass to the class constructor.

        Returns:
            An object of the required class.
        """
        return cls.classes[plugboard_class](*args, **kwargs)
