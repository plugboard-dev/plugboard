"""Provides a generic registry for Plugboard objects."""

from abc import ABC
import typing as _t

from plugboard.exceptions import RegistryError


T = _t.TypeVar("T")


class ClassRegistry(ABC, _t.Generic[T]):
    """A registry of Plugboard classes."""

    _classes: dict[_t.Hashable, type[T]]
    _duplicate_aliases: set[str] = set()

    @classmethod
    def __init_subclass__(cls) -> None:
        cls._classes = {}

    @classmethod
    def add(cls, plugboard_class: type[T], key: _t.Optional[_t.Hashable] = None) -> None:
        """Add a class to the registry.

        Args:
            plugboard_class: The class to register.
            key: Optional; The key to register the class under.
        """
        key = key or f"{plugboard_class.__module__}.{plugboard_class.__qualname__}"
        alias = plugboard_class.__qualname__
        if alias in cls._classes.keys():
            # Remove this alias to avoid ambiguity
            cls._duplicate_aliases.add(alias)
            cls._classes.pop(alias)

        cls._classes[key] = plugboard_class
        if alias not in cls._duplicate_aliases and alias != key:
            cls._classes[alias] = plugboard_class

    @classmethod
    def get(cls, plugboard_class: _t.Hashable) -> type[T]:
        """Returns a class from the registry.

        Args:
            plugboard_class: The key corresponding to the required class.

        Returns:
            The class.
        """
        try:
            return cls._classes[plugboard_class]
        except KeyError as e:
            raise RegistryError(f"Unrecognised class: {plugboard_class}") from e

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
        return cls.get(plugboard_class)(*args, **kwargs)
