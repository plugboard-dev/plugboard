"""Provides models and utilities for handling events."""

from functools import wraps
import typing as _t


class EventHandlers:
    """`EventHandlers` provides a decorator for registering event handlers."""

    # Class-level dictionary to store event handlers
    _handlers: _t.ClassVar[dict[str, dict[str, _t.Callable[..., _t.Any]]]] = {}

    @classmethod
    def register(
        cls, event_type: str
    ) -> _t.Callable[[_t.Callable[..., _t.Any]], _t.Callable[..., _t.Any]]:
        """Decorator that registers methods as handlers for specific event types.

        Args:
            event_type (str): The type of event this handler processes

        Returns:
            Callable: Decorated method
        """

        def decorator(func: _t.Callable[..., _t.Any]) -> _t.Callable[..., _t.Any]:
            @wraps(func)
            def wrapper(*args: _t.Any, **kwargs: _t.Any) -> _t.Any:
                return func(*args, **kwargs)

            # Store the handler when the decorated method is defined
            def _store_handler(owner_class: _t.Type[_t.Any]) -> None:
                class_name = owner_class.__name__
                if class_name not in cls._handlers:
                    cls._handlers[class_name] = {}

                cls._handlers[class_name][event_type] = func

            # Store handler when descriptor is accessed
            wrapper.__set_name__ = _store_handler  # type: ignore
            return wrapper

        return decorator

    @classmethod
    def get(cls, class_name: str, event_type: str) -> _t.Callable[..., _t.Any]:
        """Retrieve a handler for a specific event type.

        Args:
            class_name (str): Name of the class containing the handler
            event_type (str): Type of event to handle

        Returns:
            Callable: The event handler method

        Raises:
            KeyError: If no handler found for class or event type
        """
        if class_name not in cls._handlers:
            raise KeyError(f"No handlers registered for class '{class_name}'")

        if event_type not in cls._handlers[class_name]:
            raise KeyError(
                f"No handler found for event type '{event_type}' in class '{class_name}'"
            )

        return cls._handlers[class_name][event_type]
