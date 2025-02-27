"""Provides logging utilities."""

import logging
import os
import typing as _t

from msgspec import json
import structlog

from plugboard.utils.settings import Settings


def _serialiser(obj: _t.Any, default: _t.Callable | None) -> bytes:
    return json.encode(obj)


def configure_logging(settings: Settings) -> None:
    """Configures logging."""
    log_level = getattr(logging, settings.log_level)
    common_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.PROCESS,
            ]
        ),
    ]

    if not settings.log_structured:
        processors = common_processors + [
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        processors = common_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=_serialiser),
        ]

    structlog.configure(
        # Do not cache logger when testing: https://www.structlog.org/en/stable/testing.html
        cache_logger_on_first_use="PYTEST_CURRENT_TEST" not in os.environ,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=processors,  # type: ignore[arg-type]
        # Use BytesLoggerFactory when using msgspec serialization to bytes
        logger_factory=structlog.BytesLoggerFactory() if settings.log_structured else None,
    )
