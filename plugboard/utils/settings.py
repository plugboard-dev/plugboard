"""Provides Plugboard's settings."""

from enum import Enum
import sys
import typing as _t

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_PREFIX: str = "PLUGBOARD_"  # Prefix for environment variables.


class LogLevel(str, Enum):  # noqa: D101
    info = "INFO"
    debug = "DEBUG"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class _FeatureFlags(BaseSettings):
    """Feature flags for Plugboard.

    Attributes:
        zmq_pubsub_proxy: If set to true, runs a ZMQ proxy in a separate process for pubsub.
        multiprocessing_fork: If set to true, uses fork mode for multiprocessing.
    """

    model_config = SettingsConfigDict(env_prefix=f"{_ENV_PREFIX}FLAGS_")

    zmq_pubsub_proxy: bool = False
    multiprocessing_fork: bool = False


class _RabbitMQSettings(BaseSettings):
    """RabbitMQ settings.

    Attributes:
        url: The URL of the RabbitMQ server. Should contain credentials if required.
    """

    model_config = SettingsConfigDict(env_prefix="RABBITMQ_")

    url: _t.Optional[str] = None


class Settings(BaseSettings):
    """Settings for Plugboard.

    Attributes:
        flags: Feature flags for Plugboard.
        log_level: The log level to use.
        log_structured: Whether to render logs to JSON. Defaults to JSON if not running in a
            terminal session.
        io_read_timeout: Timeout for reading from IO streams in seconds between periodic
            status checks.
    """

    model_config = SettingsConfigDict(env_prefix=_ENV_PREFIX)

    flags: _FeatureFlags = Field(default_factory=_FeatureFlags)
    log_level: LogLevel = LogLevel.warning
    log_structured: bool = Field(default_factory=lambda: not sys.stderr.isatty())
    io_read_timeout: float = 20.0

    rabbitmq: _RabbitMQSettings = Field(default_factory=_RabbitMQSettings)
