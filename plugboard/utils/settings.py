"""Provides Plugboard's settings."""

from enum import Enum

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
        log_structured: Whether to render logs to JSON. If None, defaults to JSON if not running in
            a terminal session.
    """

    log_level: LogLevel = "WARNING"
    log_structured: bool | None = None

    model_config = SettingsConfigDict(env_prefix="plugboard_")


settings = Settings()
