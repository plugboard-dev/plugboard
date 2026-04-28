"""Provides `EventHandlers` class for registering and retrieving event handlers."""

from __future__ import annotations

from collections import defaultdict
import typing as _t

from plugboard.utils.types import AsyncCallable


if _t.TYPE_CHECKING:
    from plugboard.events.event import Event


class EventHandlers:  # pragma: no cover
    """`EventHandlers` provides a decorator for registering event handlers."""

    _handlers: _t.ClassVar[dict[str, dict[str, AsyncCallable]]] = defaultdict(dict)
    _handler_field_coverage: _t.ClassVar[dict[str, dict[str, list[str]]]] = defaultdict(dict)

    @classmethod
    def add(
        cls,
        event: _t.Type[Event] | Event,
        populates_fields: _t.Optional[list[str]] = None,
    ) -> _t.Callable[[AsyncCallable], AsyncCallable]:
        """Decorator that registers class methods as handlers for specific event types.

        Args:
            event: Event class this handler processes
            populates_fields: Optional list of fields that the handler populates

        Returns:
            Callable: Decorated method
        """

        def decorator(method: AsyncCallable) -> AsyncCallable:
            class_path = cls._get_class_path_for_method(method)
            cls._handlers[class_path][event.type] = method
            if populates_fields is not None:
                cls._handler_field_coverage[class_path][event.type] = populates_fields
            return method

        return decorator

    @staticmethod
    def _get_class_path_for_method(method: AsyncCallable) -> str:
        """Get the fully qualified path for the class containing a method."""
        module_name = method.__module__
        qualname_parts = method.__qualname__.split(".")
        class_name = qualname_parts[-2]  # Last part is the method name
        return f"{module_name}.{class_name}"

    @staticmethod
    def _iter_mro(_class: _t.Type) -> _t.Iterator[str]:
        """Iterate over class MRO, yielding fully qualified class paths."""
        for base_class in _class.__mro__:
            yield f"{base_class.__module__}.{base_class.__name__}"

    @classmethod
    def get(cls, _class: _t.Type, event: _t.Type[Event] | Event) -> AsyncCallable:
        """Retrieve a handler for a specific class and event type.

        Args:
            _class: Class to handle event for
            event: Event class or instance to handle

        Returns:
            Callable: The event handler method

        Raises:
            KeyError: If no handler found for class or event type
        """
        store = cls._handlers
        for base_path in cls._iter_mro(_class):
            if base_path in store and event.type in store[base_path]:
                return store[base_path][event.type]
        raise KeyError(
            f"No handler found for class '{_class.__name__}' and event type '{event.type}'"
        )

    @classmethod
    def get_field_coverage(cls, _class: _t.Type, event: _t.Type[Event] | Event) -> list[str]:
        """Retrieve the fields populated by the handler for a specific class and event type.

        Args:
            _class: Class to handle event for
            event: Event class or instance to handle

        Returns:
            list[str]: List of fields populated by the handler
        """
        store = cls._handler_field_coverage
        for base_path in cls._iter_mro(_class):
            if base_path in store and event.type in store[base_path]:
                return store[base_path][event.type]
        return []
