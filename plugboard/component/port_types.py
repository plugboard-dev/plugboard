"""Type declarations and compiled, non-coercing validators for component ports."""

from collections.abc import Callable, Iterable, Mapping
from types import UnionType
import typing as _t

from plugboard.exceptions import IOSetupError, ValidationError


PortDeclaration = Iterable[str] | Mapping[str, _t.Any]
RuntimeValidation = _t.Literal["off", "shallow", "deep"]
_Validator = Callable[[_t.Any, str], None]
_CONTAINERS = {list: 1, dict: 2, set: 1, frozenset: 1, tuple: None}
_UNIONS = (UnionType, _t.Union)


def type_name(hint: _t.Any) -> str:
    """Return a readable type description suitable for state metadata."""
    hint = type(None) if hint is None else hint
    if hint is _t.Any:
        return "Any"
    if _t.get_origin(hint) is not None:
        return str(hint).removeprefix("typing.")
    if hint.__module__ == "builtins":
        return hint.__qualname__
    return f"{hint.__module__}.{hint.__qualname__}"


def normalize_ports(ports: PortDeclaration | None) -> dict[str, _t.Any]:
    """Normalize legacy names and typed mappings, rejecting unsupported hints early."""
    result: dict[str, _t.Any] = (
        dict(ports) if isinstance(ports, Mapping) else dict.fromkeys(ports or (), _t.Any)
    )
    for name, hint in result.items():
        if not isinstance(name, str):
            raise IOSetupError("Port names must be strings")
        result[name] = type(None) if hint is None else hint
        _check_hint(result[name])
    return result


def _check_hint(hint: _t.Any) -> None:
    if hint is _t.Any or hint is None:
        return
    origin, args = _t.get_origin(hint), _t.get_args(hint)
    if origin in _UNIONS:
        for arg in args:
            _check_hint(arg)
        return
    if origin in _CONTAINERS:
        arity = _CONTAINERS[origin]
        if arity is not None and args and len(args) != arity:
            raise IOSetupError(f"Invalid port type arguments: {hint!r}")
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            args = args[:1]
        for arg in args:
            _check_hint(arg)
        return
    if (
        isinstance(hint, type)
        and not _t.is_typeddict(hint)
        and not getattr(hint, "_is_protocol", False)
        and origin is None
    ):
        return
    raise IOSetupError(
        f"Unsupported port type {hint!r}; use Any, a Python class, a union, "
        "or list/dict/tuple/set/frozenset types"
    )


def is_assignable(source: _t.Any, target: _t.Any) -> bool | None:
    """Check declared compatibility; None means unspecified generic information.

    Mutable containers are invariant; tuple and frozenset are covariant.
    Any and bare generic types leave compatibility unknown.
    """
    source = type(None) if source is None else (tuple if source is _t.Tuple else source)
    target = type(None) if target is None else (tuple if target is _t.Tuple else target)
    if source is _t.Any or target is _t.Any:
        return None
    if source == target:
        return True
    source_origin, target_origin = _t.get_origin(source), _t.get_origin(target)
    source_args, target_args = _t.get_args(source), _t.get_args(target)
    if source_origin in _UNIONS:
        results = [is_assignable(arg, target) for arg in source_args]
        return False if False in results else (None if None in results else True)
    if target_origin in _UNIONS:
        results = [is_assignable(source, arg) for arg in target_args]
        return True if True in results else (None if None in results else False)
    source_cls, target_cls = source_origin or source, target_origin or target
    if not issubclass(source_cls, target_cls):
        return False
    if not target_args and target_origin is not tuple:
        # A bare target does not restrict elements.
        return True
    if not source_args and source_origin is not tuple:
        return None
    if source_cls is not target_cls:
        # Generic subclass parameters cannot be inferred from their bases here.
        return None
    if source_cls is tuple:
        return _tuple_assignable(source_args, target_args)
    if len(source_args) != len(target_args):
        return None
    results = []
    for src, dst in zip(source_args, target_args):
        results.append(is_assignable(src, dst))
        if source_cls in (list, dict, set):
            results.append(is_assignable(dst, src))
    return False if False in results else (None if None in results else True)


def _tuple_assignable(source: tuple[_t.Any, ...], target: tuple[_t.Any, ...]) -> bool | None:
    source_variadic = len(source) == 2 and source[1] is Ellipsis
    target_variadic = len(target) == 2 and target[1] is Ellipsis
    if target_variadic:
        elements = source[:1] if source_variadic else source
        results = [is_assignable(arg, target[0]) for arg in elements]
    elif source_variadic or len(source) != len(target):
        return False
    else:
        results = [is_assignable(src, dst) for src, dst in zip(source, target)]
    return False if False in results else (None if None in results else True)


def compile_validator(hint: _t.Any, *, deep: bool) -> _Validator:
    """Compile a reusable validator without copying or coercing payloads."""
    hint = type(None) if hint is None else (tuple if hint is _t.Tuple else hint)
    if hint is _t.Any:
        return lambda value, path: None
    origin, args = _t.get_origin(hint), _t.get_args(hint)
    description = type_name(hint)

    def fail(value: _t.Any, path: str) -> _t.NoReturn:
        raise ValidationError(
            f"Invalid value at {path}: expected {description}, got {type_name(type(value))}"
        )

    if origin in _UNIONS:
        validators = [compile_validator(arg, deep=deep) for arg in args]

        def validate_union(value: _t.Any, path: str) -> None:
            for validate in validators:
                try:
                    validate(value, path)
                    return
                except ValidationError:
                    pass
            fail(value, path)

        return validate_union

    cls = origin or hint
    validators = (
        [compile_validator(arg, deep=True) for arg in args if arg is not Ellipsis] if deep else []
    )

    def validate(value: _t.Any, path: str) -> None:
        if not isinstance(value, cls):
            fail(value, path)
        if not deep or origin is None:
            return
        if origin is tuple:
            variadic = len(args) == 2 and args[1] is Ellipsis
            if not variadic and len(value) != len(args):
                raise ValidationError(f"Invalid tuple length at {path}: expected {description}")
            for index, item in enumerate(value):
                validators[0 if variadic else index](item, f"{path}[{index}]")
        elif origin is dict and validators:
            for index, (key, item) in enumerate(value.items()):
                validators[0](key, f"{path}.keys[{index}]")
                validators[1](item, f"{path}.values[{index}]")
        elif validators:
            for index, item in enumerate(value):
                validators[0](item, f"{path}[{index}]")

    return validate
