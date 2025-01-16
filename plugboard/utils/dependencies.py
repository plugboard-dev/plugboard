"""Provides utilities for managing Python dependencies."""

from functools import wraps
from importlib.util import find_spec
import typing as _t


def depends_on_optional(module_name: str, extra: _t.Optional[str] = None) -> _t.Callable:
    """Decorator to check for optional dependencies.

    Args:
        module_name: The name of the module to check for.
        extra: Optional; The name of the extra that the module is associated with.
            Defaults to the module name.
    """
    if not extra:
        extra = module_name

    def decorator(func: _t.Callable) -> _t.Callable:
        @wraps(func)
        def wrapper(*args: _t.Any, **kwargs: _t.Any) -> _t.Callable:
            spec = find_spec(module_name)
            if spec is None:
                raise ImportError(
                    f"Optional dependency {module_name} not found: "
                    f"install using `pip install plugboard[{extra}]`."
                )
            else:
                return func(*args, **kwargs)

        return wrapper

    return decorator
