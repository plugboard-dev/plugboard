"""Unit tests for the shared pytest configuration."""

import typing as _t

import pytest
import uvloop

from tests import conftest


def test_pytest_asyncio_loop_factories_uses_uvloop() -> None:
    """The shared pytest-asyncio hook should configure uvloop factories."""
    assert conftest.pytest_asyncio_loop_factories(
        _t.cast(pytest.Config, None),
        _t.cast(pytest.Item, None),
    ) == {"uvloop": uvloop.new_event_loop}
