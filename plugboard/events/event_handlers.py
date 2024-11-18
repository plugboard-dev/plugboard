"""Provides `EventHandlers` class for registering and retrieving event handlers."""

from __future__ import annotations

from collections import defaultdict
import typing as _t

from plugboard.utils.types import AsyncCallable


if _t.TYPE_CHECKING:
    from plugboard.events.event import Event


class EventHandlers:
    """`EventHandlers` provides a decorator for registering event handlers."""

    _handlers: _t.ClassVar[dict[str, dict[str, AsyncCallable]]] = defaultdict(dict)

    @classmethod
    def add(cls, event: _t.Type[Event] | Event) -> _t.Callable[[AsyncCallable], AsyncCallable]:
        """Decorator that registers class methods as handlers for specific event types.

        Args:
            event: Event class this handler processes

        Returns:
            Callable: Decorated method
        """

        def decorator(method: AsyncCallable) -> AsyncCallable:
            class_path = cls._get_class_path_for_method(method)
            cls._handlers[class_path][event.type] = method
            return method

        return decorator

    @staticmethod
    def _get_class_path_for_method(method: AsyncCallable) -> str:
        """Get the fully qualified path for the class containing a method."""
        module_name = method.__module__
        qualname_parts = method.__qualname__.split(".")
        class_name = qualname_parts[-2]  # Last part is the method name
        return f"{module_name}.{class_name}"

    @classmethod
    def get(cls, _class: _t.Type, event: _t.Type[Event] | Event) -> AsyncCallable:
        """Retrieve a handler for a specific event type.

        Args:
            _class: Class to handle event for
            event: Event class or instance to handle

        Returns:
            Callable: The event handler method

        Raises:
            KeyError: If no handler found for class or event type
        """
        class_path = cls._get_class_path(_class)
        if (class_handlers := cls._handlers.get(class_path)) is None:
            raise KeyError(f"No handlers found for class '{class_path}'")
        elif (handler := class_handlers.get(event.type)) is None:
            raise KeyError(f"No handler found for class '{class_path}' and event '{event.type}'")
        return handler

    @staticmethod
    def _get_class_path(class_: _t.Type) -> str:
        """Get the fully qualified path for a class."""
        return f"{class_.__module__}.{class_.__name__}"
