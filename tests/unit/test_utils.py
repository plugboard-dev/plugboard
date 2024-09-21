"""Unit tests for the utilities."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.utils import Registry


class BaseA:
    def __init__(self, x: str) -> None:
        self.x = x


class BaseB:
    pass


class A1(BaseA):
    pass


class A2(BaseA):
    pass


class B(BaseB):
    pass


def test_registry() -> None:
    """Tests the `Registry`."""

    class RegistryA(Registry[BaseA]):
        pass

    class RegistryB(Registry[BaseB]):
        pass

    RegistryA.register(A1, "a1")
    RegistryA.register(A2, "a2")
    RegistryB.register(B, B)

    # Check that the classes were registered correctly
    assert RegistryA.get_class("a1") == A1
    assert RegistryA.get_class("a2") == A2
    assert RegistryB.get_class(B) == B
    with pytest.raises(KeyError):
        RegistryA.get_class(B)

    # Check that classes can be built
    a1 = RegistryA.build_object("a1", x="one")
    assert isinstance(a1, A1)
    assert a1.x == "one"
    a2 = RegistryA.build_object("a2", x="two")
    assert isinstance(a2, A2)
    assert a2.x == "two"
    assert isinstance(RegistryB.build_object(B), B)
    with pytest.raises(KeyError):
        RegistryA.build_object(B)
