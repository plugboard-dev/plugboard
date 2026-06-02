"""Unit tests for the shared pytest configuration."""

import uvloop


def test_event_loop_policy_uses_uvloop(event_loop_policy: object) -> None:
    """The shared pytest-asyncio fixture should configure uvloop policy."""
    assert isinstance(event_loop_policy, uvloop.EventLoopPolicy)
