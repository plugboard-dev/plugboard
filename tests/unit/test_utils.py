"""Unit tests for the utilities."""
# ruff: noqa: D101,D102,D103

import pytest
import ray

from plugboard.exceptions import RegistryError
from plugboard.utils import (
    ClassRegistry,
    build_actor_wrapper,
    depends_on_optional,
    gather_except,
    is_on_ray_worker,
)


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


class C:
    def __init__(self) -> None:
        self.x = 0

    def add(self, y: int) -> None:
        self.x += y

    async def add_async(self, y: int) -> None:
        self.x += y


class D:
    c: C = C()

    @property
    def x(self) -> int:
        return self.c.x

    @x.setter
    def x(self, value: int) -> None:
        self.c.x = value


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


@pytest.mark.asyncio
async def test_actor_wrapper() -> None:
    """Tests the `build_actor_wrapper` utility."""
    WrappedC = build_actor_wrapper(C)
    WrappedD = build_actor_wrapper(D)

    c = WrappedC()
    d = WrappedD()

    # Must be able to call synchronous methods on target
    c.add(5)  # type: ignore
    assert c._self.x == 5
    # Must be able to call asynchronous methods on target
    await c.add_async(10)  # type: ignore
    assert c._self.x == 15

    # Must be able to access properties on target
    assert d.getattr("x") == 0
    d.setattr("x", 25)
    assert d.getattr("x") == 25
    assert d._self.c.x == 25

    # Must be able to call synchronous methods on nested target
    d.c_add(5)  # type: ignore
    assert d._self.c.x == 30
    # Must be able to call asynchronous methods on nested target
    await d.c_add_async(10)  # type: ignore
    assert d._self.c.x == 40


def test_depends_on_optional() -> None:
    """Tests the `depends_on_optional` utility."""

    @depends_on_optional("unknown_package")
    def func_not_ok(x: int) -> int:
        return x

    @depends_on_optional("pydantic")
    def func_ok(x: int) -> int:
        return x

    # Must raise ImportError if the optional dependency is not found
    with pytest.raises(ImportError) as e:
        func_not_ok(1)
        assert "plugboard[unknown_package]" in str(e.value)

    # Must not raise ImportError if the optional dependency is found
    assert func_ok(1) == 1


@pytest.mark.asyncio
async def test_gather_except() -> None:
    """Tests the `gather_except` utility."""

    async def coro_ok() -> int:
        return 1

    async def coro_err() -> int:
        raise ValueError("Error")

    # Must return the results if all coroutines are successful
    results = await gather_except(coro_ok(), coro_ok())
    assert results == [1, 1]

    # Must raise an exception if any coroutines raise an exception
    with pytest.raises(ExceptionGroup) as e:
        await gather_except(coro_ok(), coro_err())
    assert len(e.value.exceptions) == 1
    assert isinstance(e.value.exceptions[0], ValueError)


def test_is_on_ray() -> None:
    """Tests the `is_on_ray_worker` utility."""
    assert is_on_ray_worker() is False

    @ray.remote
    def remote_func() -> bool:
        return is_on_ray_worker()

    assert ray.get(remote_func.remote()) is True
