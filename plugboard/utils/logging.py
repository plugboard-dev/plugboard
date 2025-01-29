"""Provides logging utilities."""

import logging
import sys
import typing as _t

from msgspec import json
import structlog

from plugboard.utils.settings import settings


def _serialiser(obj: _t.Any, default: _t.Callable | None) -> bytes:
    return json.encode(obj)


def configure_logging() -> None:
    """Configures logging."""
    log_level = getattr(logging, settings.log_level)
    # If log_structured is None, default to JSON logs if we're not running in a terminal session
    log_structured = (
        settings.log_structured if settings.log_structured is not None else not sys.stderr.isatty()
    )
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

    if not log_structured:
        processors = common_processors + [
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        processors = common_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=_serialiser),
        ]

    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=processors,
        # Use BytesLoggerFactory when using msgspec serialization to bytes
        logger_factory=structlog.BytesLoggerFactory() if log_structured else None,
    )
