"""Provides utility functions for working with Plugboard components."""

from __future__ import annotations

import inspect
from string import Template
import typing as _t

from plugboard.component.component import Component, ComponentRegistry
from plugboard.component.io_controller import IOController
from plugboard.utils import gen_rand_str


_FuncT = _t.TypeVar(
    "_FuncT",
    bound=_t.Callable[..., _t.Union[dict[str, _t.Any], _t.Awaitable[dict[str, _t.Any]]]],
)

_FUNC_COMPONENT_DOC_TEMPLATE = Template(
    """Component for wrapped function $name.

    This component calls the wrapped function in the step method.

    Documentation for wrapped function follows:

    $doc
    """
)


def component(
    inputs: _t.Optional[_t.Any] = None, outputs: _t.Optional[_t.Any] = None
) -> _t.Callable[[_FuncT], "ComponentDecoratorHelper"]:
    """A decorator to auto generate a Plugboard component from a function.

    The wrapped function will be added to a dynamically created component class
    as the step method. The returned helper class can either be called directly,
    retaining the original behaviour of the wrapped function; or can be used to
    create a component instance.

    Args:
        inputs: The input schema or schema factory for the component.
        outputs: The output schema or schema factory for the component.

    Returns:
        A helper class which can be used to both call the original function and create
        an instance of the component class.
    """

    def decorator(func: _FuncT) -> ComponentDecoratorHelper:
        comp_cls = _make_component_class(func, inputs, outputs)
        return ComponentDecoratorHelper(func, comp_cls)

    return decorator


class ComponentDecoratorHelper:
    """Stores wrapped function and dynamically created component class."""

    def __init__(self, func: _FuncT, component_cls: _t.Type[Component]) -> None:  # noqa: D107
        self._func: _FuncT = func
        self._component_cls: _t.Type[Component] = component_cls

    def component(self, name: _t.Optional[str] = None, **kwargs: _t.Any) -> Component:
        """Creates an instance of the component class for the wrapped function."""
        _name = name or f"{self._func.__name__}_{gen_rand_str(6)}"
        return self._component_cls(name=_name, **kwargs)

    def __call__(self, *args: _t.Any, **kwargs: _t.Any) -> _t.Any:
        """Calls the wrapped function directly."""
        return self._func(*args, **kwargs)


def _make_component_class(
    func: _FuncT, inputs: _t.Optional[_t.Any], outputs: _t.Optional[_t.Any]
) -> _t.Type[Component]:
    """Creates a Plugboard component class from a function."""
    _async_func: _t.Callable[..., _t.Awaitable[dict[str, _t.Any]]] = _ensure_async_callable(func)

    class _FuncComponent(Component):
        __doc__ = _FUNC_COMPONENT_DOC_TEMPLATE.substitute(
            name=func.__name__, doc=func.__doc__ or "Undocumented..."
        )

        io = IOController(inputs=inputs, outputs=outputs)
        wrapped_function: _FuncT = func

        async def step(self) -> _t.Any:
            fn_in = {field: getattr(self, field) for field in self.io.inputs}
            fn_out = await _async_func(**fn_in)
            if not isinstance(fn_out, dict):
                raise ValueError(f"Wrapped function must return a dict, got {type(fn_out)}")
            for k, v in fn_out.items():
                setattr(self, k, v)

    ComponentRegistry.add(_FuncComponent, key=func.__name__)
    ComponentRegistry.add(_FuncComponent, key=f"{func.__module__}.{func.__name__}")

    return _FuncComponent


def _ensure_async_callable(func: _FuncT) -> _t.Callable[..., _t.Awaitable[dict[str, _t.Any]]]:
    if inspect.iscoroutinefunction(func):
        return func

    async def _async_func(*args: _t.Any, **kwargs: _t.Any) -> dict[str, _t.Any]:
        return func(*args, **kwargs)  # type: ignore[return-value]

    return _async_func
