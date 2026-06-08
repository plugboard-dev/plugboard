"""Unit tests for the shared pytest configuration."""

import uvloop


def test_asyncio_loop_factory_uses_uvloop(_asyncio_loop_factory: object) -> None:
    """The shared pytest-asyncio fixture should configure uvloop loop factory."""
    assert _asyncio_loop_factory is uvloop.new_event_loop
