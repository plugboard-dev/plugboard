"""Unit tests for the utilities."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.exceptions import RegistryError
from plugboard.utils import ClassRegistry


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
    """Tests the `ClassRegistry`."""

    class RegistryA(ClassRegistry[BaseA]):
        pass

    class RegistryB(ClassRegistry[BaseB]):
        pass

    RegistryA.add(A1, "a1")
    RegistryA.add(A2, "a2")
    RegistryB.add(B, B)

    # Check that the classes were registered correctly
    assert RegistryA.get("a1") == A1
    assert RegistryA.get("a2") == A2
    assert RegistryB.get(B) == B
    with pytest.raises(RegistryError):
        RegistryA.get(B)

    # Check that classes can be built
    a1 = RegistryA.build("a1", x="one")
    assert isinstance(a1, A1)
    assert a1.x == "one"
    a2 = RegistryA.build("a2", x="two")
    assert isinstance(a2, A2)
    assert a2.x == "two"
    assert isinstance(RegistryB.build(B), B)
    with pytest.raises(RegistryError):
        RegistryA.build(B)


def test_registry_default_key() -> None:
    """Tests the default keys in the `ClassRegistry`."""

    class RegistryA(ClassRegistry[BaseA]):
        pass

    RegistryA.add(A1)
    RegistryA.add(A2)
    # Full module path and class name is used as the key
    assert RegistryA.get("tests.unit.test_utils.A1") == A1
    assert RegistryA.get("tests.unit.test_utils.A2") == A2
    # Class name is also an alias key
    assert RegistryA.get("A1") == A1
    assert RegistryA.get("A2") == A2

    # Adding a class again will remove the alias key
    RegistryA.add(A1)
    with pytest.raises(RegistryError):
        RegistryA.get("A1")
    assert RegistryA.get("tests.unit.test_utils.A1") == A1
    assert RegistryA.get("A2") == A2

    # Adding the class again will still not add the alias key
    RegistryA.add(A1)
    with pytest.raises(RegistryError):
        RegistryA.get("A1")
