"""Provides utility functions for working with Plugboard components."""

import typing as _t

from plugboard.component.component import Component, ComponentRegistry
from plugboard.component.io_controller import IOController
from plugboard.utils import gen_rand_str


def _make_component_class(
    func: _t.Callable, inputs: _t.Optional[_t.Any], outputs: _t.Optional[_t.Any]
) -> _t.Type[Component]:
    """Creates a Plugboard component class from a function."""

    class FuncComponent(Component):
        io = IOController(inputs=inputs, outputs=outputs)

        async def step(self) -> _t.Any:
            fn_in = {field: getattr(self, field) for field in self.io.inputs}
            fn_out = await func(**fn_in)
            if not isinstance(fn_out, dict):
                raise ValueError(f"Wrapped function must return a dict, got {type(fn_out)}")
            for k, v in fn_out.items():
                setattr(self, k, v)

    FuncComponent.__name__ = f"FuncComponent__{func.__name__}"
    FuncComponent.__doc__ = func.__doc__

    ComponentRegistry.add(FuncComponent)

    return FuncComponent


class ComponentDecoratorHelper:
    """Stores wrapped function and dynamically created component class."""

    def __init__(self, func: _t.Callable, component_cls: _t.Type[Component]) -> None:
        self._func = func
        self._component_cls = component_cls

    def create_component(self, name: _t.Optional[str] = None, **kwargs: _t.Any) -> Component:
        """Creates an instance of the component class for the wrapped function."""
        _name = name or f"{self._func.__name__}_{gen_rand_str(6)}"
        return self._component_cls(name=_name, **kwargs)

    def __call__(self, *args: _t.Any, **kwargs: _t.Any) -> _t.Any:  # noqa: D102
        return self._func(*args, **kwargs)


def component(
    inputs: _t.Optional[_t.Any] = None, outputs: _t.Optional[_t.Any] = None
) -> ComponentDecoratorHelper:
    """A decorator to auto generate a Plugboard component from a function.

    The wrapped function will be added to a dynamically created component class
    as the step method.

    Args:
        inputs: The input schema or schema factory for the component.
        outputs: The output schema or schema factory for the component.

    Returns:
        The dynamically created component class.
    """

    def decorator(func: _t.Callable) -> _t.Any:
        comp_cls = _make_component_class(func, inputs, outputs)
        return ComponentDecoratorHelper(func, comp_cls)

    return decorator
