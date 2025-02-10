"""Provides Plugboard's settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_PREFIX: str = "PLUGBOARD_"  # Prefix for environment variables.


class _FeatureFlags(BaseSettings):
    """Feature flags for Plugboard.

    Attributes:
        zmq_pubsub_proxy: If set to true, runs a ZMQ proxy in a separate process for pubsub.
    """

    model_config = SettingsConfigDict(env_prefix=f"{_ENV_PREFIX}FLAGS_")

    zmq_pubsub_proxy: bool = False
    multiprocessing_fork: bool = False


class Settings(BaseSettings):
    """Settings for Plugboard.

    Attributes:
        flags: Feature flags for Plugboard.
    """

    model_config = SettingsConfigDict(env_prefix=_ENV_PREFIX)

    flags: _FeatureFlags = Field(default_factory=_FeatureFlags)
