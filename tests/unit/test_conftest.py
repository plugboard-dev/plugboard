"""Unit tests for the shared pytest configuration."""

import typing as _t
from unittest.mock import MagicMock

import pytest
import uvloop

from tests import conftest


def test_pytest_asyncio_loop_factories_uses_uvloop() -> None:
    """The shared pytest-asyncio hook should configure uvloop factories."""
    assert conftest.pytest_asyncio_loop_factories(
        MagicMock(spec=pytest.Config),
        MagicMock(spec=pytest.Item),
    ) == {"uvloop": uvloop.new_event_loop}


def test_event_loop_policy_fallback_uses_uvloop() -> None:
    """Older pytest-asyncio releases should still get uvloop via the fallback fixture."""
    if conftest._HAS_LOOP_FACTORY_HOOK:
        pytest.skip("Installed pytest-asyncio already provides the loop-factory hook")

    event_loop_policy = _t.cast(_t.Any, conftest.event_loop_policy)
    assert isinstance(event_loop_policy.__wrapped__(), uvloop.EventLoopPolicy)
