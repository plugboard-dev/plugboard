"""Tests for optional port types, compatibility, inheritance, and value validation."""

from abc import ABC
import typing as _t
from unittest.mock import Mock, patch

import msgspec
import pytest

from plugboard.component import Component, IOController as IO, component
from plugboard.component.port_types import compile_validator, is_assignable
from plugboard.connector import AsyncioConnector
from plugboard.exceptions import IOSetupError, ValidationError
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec


class Animal:
    """Base payload class."""


class Dog(Animal):
    """A narrower payload class."""


@pytest.mark.parametrize(
    "source,target,expected",
    [
        (Dog, Animal, True),
        (Animal, Dog, False),
        (int, str, False),
        (int, float, False),
        (bool, int, True),
        (_t.Any, int, None),
        (int, _t.Any, None),
        (str, str | None, True),
        (str | None, str, False),
        (int | str, str | int | None, True),
        (_t.Union[int, str], int, False),
        (list[Dog], list[Animal], False),
        (list[int], list[int], True),
        (list[None], list[type(None)], True),
        (list[_t.Any], list[int], None),
        (list, list[int], None),
        (list[int], list, True),
        (dict[str, int], dict[str, str], False),
        (dict[str, Dog], dict[str, Animal], False),
        (frozenset[Dog], frozenset[Animal], True),
        (set[Dog], set[Animal], False),
        (tuple[Dog, int], tuple[Animal, int], True),
        (tuple[Dog, Dog], tuple[Animal, ...], True),
        (tuple[Dog, ...], tuple[Animal, ...], True),
        (tuple[int, ...], tuple[int, int], False),
        (tuple[int], tuple[int, int], False),
        (tuple[()], tuple[int, ...], True),
        (tuple[int], tuple[()], False),
        (tuple, tuple[int], None),
        (_t.Tuple, tuple[int], None),
        (tuple[int], _t.Tuple, True),
        (list[int], object, True),
    ],
)
def test_connection_compatibility(source: _t.Any, target: _t.Any, expected: bool | None) -> None:
    """Connections respect nominal subtyping, unions, and container variance."""
    assert is_assignable(source, target) is expected


def test_legacy_and_mapping_declarations() -> None:
    """Lists retain Any semantics and controllers own their normalized mappings."""
    legacy = IO(inputs=["x"], outputs=("y",))
    assert legacy.inputs == ["x"]
    assert legacy.input_types == {"x": _t.Any}
    assert legacy.output_types == {"y": _t.Any}
    assert "input_types" not in legacy.dict()
    types = {"x": int, "optional": None}
    typed = IO(inputs=types)
    types["x"] = str
    assert typed.input_types == {"x": int, "optional": type(None)}
    assert typed.inputs == ["x", "optional"]
    assert msgspec.json.decode(msgspec.json.encode(typed.dict()))["input_types"]["x"] == "int"


@pytest.mark.parametrize(
    "hint", ["int", 123, list[_t.ForwardRef("Missing")], _t.Literal[1], _t.Callable]
)
def test_unsupported_types(hint: _t.Any) -> None:
    """Unsupported declarations fail at setup even when runtime validation is off."""
    with pytest.raises(IOSetupError, match="Unsupported port type"):
        IO(inputs={"x": hint})


def test_invalid_mode() -> None:
    """Typos in validation policy fail immediately."""
    with pytest.raises(ValueError, match="Unknown runtime validation mode"):
        IO(runtime_validation=_t.cast(_t.Any, "typo"))


def test_inheritance_and_instance_copy() -> None:
    """Inherited ports keep types, and legacy redeclarations do not erase them."""

    class Parent(Component):
        io = IO(inputs={"x": int}, outputs={"y": list[str]}, runtime_validation="deep")

    class Child(Parent):
        io = IO(inputs=["x", "z"], runtime_validation="shallow", validate_outputs=True)

    child = Child(name="child")
    assert child.io.input_types == {"x": int, "z": _t.Any}
    assert child.io.output_types == {"y": list[str]}
    assert child.io.runtime_validation == "shallow"
    assert child.io.validate_outputs
    assert child.io.input_types is not Child.io.input_types

    class Grandchild(Child):
        pass

    assert Grandchild.io.input_types == child.io.input_types
    assert Grandchild.io.runtime_validation == "shallow"


def test_conflicting_inheritance() -> None:
    """Both overrides and conflicting multiple inheritance are rejected."""

    class Left(Component, ABC):
        io = IO(inputs={"x": int})

    class Right(Component, ABC):
        io = IO(inputs={"x": str})

    with pytest.raises(IOSetupError, match="Conflicting inherited types"):

        class Override(Left):
            io = IO(inputs={"x": str})

    with pytest.raises(IOSetupError, match="Conflicting inherited types"):

        class Combined(Left, Right):
            pass


def test_legacy_dynamic_names_and_mixin() -> None:
    """Names added to legacy lists and declarations supplied by mixins still work."""

    class Parent(Component):
        io = IO(outputs=["x"])

    Parent.io.outputs.append("y")
    assert Parent(name="parent").io.output_types == {"x": _t.Any, "y": _t.Any}

    class Child(Parent):
        pass

    assert Child.io.output_types == {"x": _t.Any, "y": _t.Any}

    class Mixin:
        io = IO(outputs={"x": int})

    class Mixed(Mixin, Component):
        pass

    assert Mixed(name="mixed").io.output_types == {"x": int}


@pytest.mark.parametrize(
    "hint,value",
    [
        (int, 1),
        (int, True),
        (Animal, Dog()),
        (str | None, None),
        (list[int | None], [1, None]),
        (list[None], [None]),
        (dict[str, list[int]], {"x": [1, 2]}),
        (tuple[int, str], (1, "x")),
        (tuple[int, ...], (1, 2, 3)),
        (tuple[()], ()),
        (_t.Tuple, (1, "x")),
        (set[int], {1, 2}),
        (frozenset[str], frozenset({"x"})),
        (_t.Any, object()),
    ],
)
def test_deep_valid_values(hint: _t.Any, value: _t.Any) -> None:
    """Validation supports the declared subset and does not transform values."""
    compile_validator(hint, deep=True)(value, "component.port")


@pytest.mark.parametrize(
    "hint,value,path",
    [
        (int, "1", "component.port"),
        (float, 1, "component.port"),
        (list[int], ["1"], "component.port[0]"),
        (list[None], [1], "component.port[0]"),
        (dict[str, list[int]], {"x": ["1"]}, "component.port.values[0][0]"),
        (dict[str, int], {1: 2}, "component.port.keys[0]"),
        (tuple[int, str], (1, 2), "component.port[1]"),
        (tuple[int, ...], (1, "2"), "component.port[1]"),
        (tuple[()], (1,), "component.port"),
        (set[int], {"1"}, "component.port[0]"),
        (str | None, 1, "component.port"),
    ],
)
def test_deep_invalid_values(hint: _t.Any, value: _t.Any, path: str) -> None:
    """Nested validation failures include a useful path without coercion."""
    with pytest.raises(ValidationError) as exc:
        compile_validator(hint, deep=True)(value, "component.port")
    assert path in str(exc.value)


def test_runtime_policy_and_compile_once() -> None:
    """Off does not compile validators; active policies reuse them for every value."""
    with patch(
        "plugboard.component.io_controller.compile_validator", wraps=compile_validator
    ) as spy:
        off = IO(inputs={"x": int}, outputs={"y": str}, validate_outputs=True)
        off.validate_inputs({"x": "anything"})
        assert not spy.called
        deep = IO(inputs={"x": list[int]}, runtime_validation="deep")
        count = spy.call_count
        deep.validate_inputs({"x": [1]})
        deep.validate_inputs({"x": [2]})
        assert spy.call_count == count

    shallow = IO(inputs={"x": list[int]}, runtime_validation="shallow")
    shallow.validate_inputs({"x": ["unchecked contents"]})
    with pytest.raises(ValidationError, match="expected list"):
        shallow.validate_inputs({"x": "wrong outer type"})


def test_binding_and_output_fanout() -> None:
    """Missing inputs are skipped, supplied None is checked, and outputs validate once."""

    class Typed(Component):
        io = IO(
            inputs={"x": int},
            outputs={"y": int},
            runtime_validation="deep",
            validate_outputs=True,
        )

        async def step(self) -> None:
            self.y = self.x

    comp = Typed(name="typed")
    comp._bind_inputs()
    assert not comp._field_inputs_ready
    comp.x = None
    with pytest.raises(ValidationError, match=r"typed.x \(input\).*expected int.*NoneType"):
        comp._bind_inputs()
    comp.x = 1
    comp._bind_inputs()
    comp.y = "wrong"
    with pytest.raises(ValidationError, match=r"typed.y \(output\).*expected int.*str"):
        comp._bind_outputs()
    assert not comp.io.buf_fields["output"]
    comp.y = 1
    validate = Mock(wraps=comp.io._output_validators["y"])
    comp.io._output_validators["y"] = validate
    comp.io._output_channels = {("y", "a"): Mock(), ("y", "b"): Mock()}
    comp._bind_outputs()
    assert validate.call_count == 1


def test_output_checking_is_opt_in() -> None:
    """Enabling input checks alone does not compile output checks."""
    io = IO(inputs={"x": int}, outputs={"y": int}, runtime_validation="deep")
    assert io._input_validators
    assert not io._output_validators
    io.validate_output_values({"y": "unchecked"})


def test_initialization_checks_each_edge_and_allows_any() -> None:
    """Fan-in/fan-out checks report every incompatible edge and allow untyped ports."""

    class IntSource(Component):
        io = IO(outputs={"value": int})

    class StringSource(Component):
        io = IO(outputs={"value": str})

    class IntSink(Component):
        io = IO(inputs={"value": int})

    class UntypedSink(Component):
        io = IO(inputs=["value"])

    components = [
        IntSource(name="numbers"),
        StringSource(name="strings"),
        IntSink(name="sink_a"),
        IntSink(name="sink_b"),
        UntypedSink(name="untyped"),
    ]
    connectors = [
        AsyncioConnector(ConnectorSpec(source=f"{source}.value", target=f"{target}.value"))
        for source, target in (
            ("numbers", "sink_a"),
            ("strings", "sink_a"),
            ("strings", "sink_b"),
            ("strings", "untyped"),
        )
    ]
    process = LocalProcess(components, connectors)
    with pytest.raises(ValidationError) as exc:
        process._validate_io_types()
    assert str(exc.value).count("Incompatible port types") == 2
    assert "strings.value (str) -> sink_a.value (int)" in str(exc.value)
    assert "strings.value (str) -> sink_b.value (int)" in str(exc.value)
    assert "untyped" not in str(exc.value)
    process.connectors = {connectors[0].id: connectors[0], connectors[-1].id: connectors[-1]}
    process._validate_io_types()


def test_mapping_declarations_on_decorated_components() -> None:
    """Function components accept mappings without inferring types from annotations."""

    @component(inputs={"x": int}, outputs={"y": str})
    async def transform(x: int) -> dict[str, str]:
        return {"y": str(x)}

    comp = transform.component(name="transform")
    assert comp.io.input_types == {"x": int}
    assert comp.io.output_types == {"y": str}

    class AnnotationsOnly(Component):
        io = IO(inputs=["x"])
        x: int

    assert AnnotationsOnly.io.input_types == {"x": _t.Any}
