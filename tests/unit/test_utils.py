"""Unit tests for the utilities."""
# ruff: noqa: D101,D102,D103

import pytest

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
    """Tests the `Registry`."""

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
    with pytest.raises(KeyError):
        RegistryA.get(B)

    # Check that classes can be built
    a1 = RegistryA.build("a1", x="one")
    assert isinstance(a1, A1)
    assert a1.x == "one"
    a2 = RegistryA.build("a2", x="two")
    assert isinstance(a2, A2)
    assert a2.x == "two"
    assert isinstance(RegistryB.build(B), B)
    with pytest.raises(KeyError):
        RegistryA.build(B)
