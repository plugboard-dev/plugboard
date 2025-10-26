"""Provides utility functions for working with Plugboard components."""

import typing as _t

from plugboard.component.component import Component
from plugboard.component.io_controller import IOController
from plugboard.utils import gen_rand_str


def component(inputs: _t.Optional[_t.Any] = None, outputs: _t.Optional[_t.Any] = None) -> _t.Any:
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

        def _helper(name: _t.Optional[str] = None, **kwargs: _t.Any) -> _t.Any:
            _name = name or f"{func.__name__}_{gen_rand_str(6)}"
            return FuncComponent(name=_name, **kwargs)

        return _helper

    return decorator
