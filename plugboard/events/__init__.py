"""Provides models and utilities for handling events."""

from collections import defaultdict
import typing as _t


class EventHandlers:
    """`EventHandlers` provides a decorator for registering event handlers."""

    # Class-level dictionary to store event handlers
    _handlers: _t.ClassVar[dict[str, dict[str, _t.Callable[..., _t.Any]]]] = defaultdict(dict)

    @staticmethod
    def _get_class_path(func: _t.Callable[..., _t.Any]) -> str:
        """Get the fully qualified path for the class containing the handler."""
        module_name = func.__module__
        qualname_parts = func.__qualname__.split(".")
        class_name = qualname_parts[-2]  # Last part is the method name
        return f"{module_name}.{class_name}"

    @classmethod
    def add(
        cls, event_type: str
    ) -> _t.Callable[[_t.Callable[..., _t.Any]], _t.Callable[..., _t.Any]]:
        """Decorator that registers methods as handlers for specific event types.

        Args:
            event_type (str): The type of event this handler processes

        Returns:
            Callable: Decorated method
        """

        def decorator(func: _t.Callable[..., _t.Any]) -> _t.Callable[..., _t.Any]:
            class_path = cls._get_class_path(func)
            cls._handlers[class_path][event_type] = func
            return func

        return decorator

    @classmethod
    def get(cls, class_path: str, event_type: str) -> _t.Callable[..., _t.Any]:
        """Retrieve a handler for a specific event type.

        Args:
            class_path (str): Fully qualified path of the class (module.class)
            event_type (str): Type of event to handle

        Returns:
            Callable: The event handler method

        Raises:
            KeyError: If no handler found for class or event type
        """
        if (class_handlers := cls._handlers.get(class_path)) is None:
            raise KeyError(f"No handlers found for class '{class_path}'")
        elif (handler := class_handlers.get(event_type)) is None:
            raise KeyError(f"No handler found for class '{class_path}' and event '{event_type}'")
        return handler
