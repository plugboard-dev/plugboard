"""Unit tests for the shared pytest configuration."""

import asyncio
import os

import pytest
import uvloop

from plugboard.connector import AsyncioConnector, ZMQConnector
from plugboard.utils.di import DI
from plugboard.utils.settings import Settings
from tests import conftest


async def test_tests_run_on_uvloop() -> None:
    """Tests should run on a uvloop event loop, supplied by the loop factory hook."""
    assert isinstance(asyncio.get_running_loop(), uvloop.Loop)


@pytest.mark.parametrize("proxy_enabled", [False, True])
@pytest.mark.parametrize("raise_error", [False, True])
def test_override_settings_restores_provider(
    monkeypatch: pytest.MonkeyPatch, proxy_enabled: bool, raise_error: bool
) -> None:
    """Settings overrides respect explicit flags and clean up even when a test fails."""
    monkeypatch.setenv("PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY", str(not proxy_enabled))
    monkeypatch.setenv("PLUGBOARD_IO_READ_TIMEOUT", "5.0")
    original = DI.settings.resolve_sync()
    environment = dict(os.environ)
    settings = Settings.model_validate({"flags": {"zmq_pubsub_proxy": proxy_enabled}})

    def exercise_override() -> None:
        with conftest.override_settings(settings):
            assert DI.settings.resolve_sync() is settings
            assert settings.flags.zmq_pubsub_proxy is proxy_enabled
            assert settings.io_read_timeout == 5.0
            assert dict(os.environ) == environment
            if raise_error:
                raise RuntimeError("simulated test failure")

    if raise_error:
        with pytest.raises(RuntimeError, match="simulated test failure"):
            exercise_override()
    else:
        exercise_override()

    assert DI.settings.resolve_sync() is original
    assert dict(os.environ) == environment


@pytest.mark.parametrize(
    "case",
    [
        conftest.ConnectorCase(AsyncioConnector),
        conftest.ConnectorCase(ZMQConnector, False),
        conftest.ConnectorCase(ZMQConnector, True),
    ],
    ids=conftest.connector_case_id,
)
@pytest.mark.parametrize("raise_error", [False, True])
def test_configured_connector_restores_settings(
    monkeypatch: pytest.MonkeyPatch, case: conftest.ConnectorCase, raise_error: bool
) -> None:
    """Connector cases override only explicit flags and restore settings even on failure."""
    monkeypatch.setenv("PLUGBOARD_FLAGS_ZMQ_PUBSUB_PROXY", str(not case.zmq_pubsub_proxy))
    monkeypatch.setenv("PLUGBOARD_IO_READ_TIMEOUT", "5.0")
    original = DI.settings.resolve_sync()
    environment = dict(os.environ)

    def exercise_case() -> None:
        with conftest.configured_connector(case) as connector_cls:
            assert connector_cls is case.connector_cls
            settings = DI.settings.resolve_sync()
            if case.zmq_pubsub_proxy is None:
                assert settings is original
            else:
                assert settings.flags.zmq_pubsub_proxy is case.zmq_pubsub_proxy
                assert settings.io_read_timeout == 5.0
            assert dict(os.environ) == environment
            if raise_error:
                raise RuntimeError("simulated test failure")

    if raise_error:
        with pytest.raises(RuntimeError, match="simulated test failure"):
            exercise_case()
    else:
        exercise_case()

    assert DI.settings.resolve_sync() is original
    assert dict(os.environ) == environment
