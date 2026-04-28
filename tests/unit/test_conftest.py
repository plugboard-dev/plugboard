"""Unit tests for the shared pytest configuration."""

import uvloop

from tests import conftest


def test_pytest_asyncio_loop_factories_uses_uvloop() -> None:
    """The shared pytest-asyncio hook should configure uvloop factories."""
    assert conftest.pytest_asyncio_loop_factories() == {"uvloop": uvloop.new_event_loop}
