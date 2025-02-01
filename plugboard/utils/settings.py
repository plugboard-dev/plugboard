"""Provides Plugboard's settings."""

from enum import Enum
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):  # noqa: D101
    info = "INFO"
    debug = "DEBUG"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class Settings(BaseSettings):
    """Settings for Plugboard.

    Attributes:
        log_level: The log level to use.
        log_structured: Whether to render logs to JSON. Defaults to JSON if not running in a
            terminal session.
    """

    log_level: LogLevel = LogLevel.warning
    log_structured: bool = Field(default_factory=lambda: not sys.stderr.isatty())

    model_config = SettingsConfigDict(env_prefix="plugboard_")


settings = Settings()
