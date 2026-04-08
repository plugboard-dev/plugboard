"""Process validator registry and decorator."""

from __future__ import annotations

from collections.abc import Callable
import typing as _t


_Fn = _t.TypeVar("_Fn", bound=Callable[[dict[str, _t.Any]], list[str]])


class _ValidatorRegistry:
    """Singleton registry for process validator functions.

    Validators are stored in registration order and all executed by
    `validate_process`. Use the module-level `validator` decorator to
    register; do not instantiate this class directly.
    """

    _instance: _ValidatorRegistry | None = None
    _validators: list[Callable[[dict[str, _t.Any]], list[str]]]

    def __new__(cls) -> _ValidatorRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._validators = []
        return cls._instance

    def register(self, func: _Fn) -> _Fn:
        """Append *func* to the registry and return it unchanged."""
        self._validators.append(func)
        return func

    def run_all(self, process_dict: dict[str, _t.Any]) -> list[str]:
        """Invoke every validator, collecting all errors before raising.

        Running every validator before raising means the caller receives
        all problems at once rather than having to fix them one by one.
        """
        errors: list[str] = []
        for fn in self._validators:
            errors.extend(fn(process_dict))
        return errors

    def __len__(self) -> int:
        return len(self._validators)

    def __repr__(self) -> str:
        names = [fn.__name__ for fn in self._validators]
        return f"{type(self).__name__}({names!r})"


_registry = _ValidatorRegistry()


def validator(func: _Fn) -> _Fn:
    """Decorator: register *func* as a process validator.

    Validators are called in registration order when `validate_process`
    is invoked. Raise an exception inside the validator to signal an
    invalid process.

    Example::

        @validator
        def check_no_cycles(connectors: ConnectorMap) -> None:
            if cycles := _find_cycles(connectors):
                raise ValueError(f"Cycle detected involving: {cycles}")
    """
    return _registry.register(func)


def validate_process(process_dict: dict[str, _t.Any]) -> list[str]:
    """Run all registered validators against the given process.

    New validators are picked up automatically via the `@validator`
    decorator; this function never needs to be modified directly.
    """
    return _registry.run_all(process_dict)
