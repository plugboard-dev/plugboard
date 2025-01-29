"""Provides logging utilities."""

import logging
import sys

from msgspec import json
import structlog


def configure_logging() -> None:
    """Configures logging."""
    common_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.PROCESS,
                structlog.processors.CallsiteParameter.THREAD_NAME,
            ]
        ),
        structlog.processors.StackInfoRenderer(),
    ]

    if sys.stderr.isatty():
        # Pretty printing when we run in a terminal session.
        processors = common_processors + [
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        # Otherwise print JSON
        processors = common_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=json.encode),
        ]

    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=processors,
        # Use BytesLoggerFactory when using msgspec serialization to bytes
        logger_factory=structlog.BytesLoggerFactory() if not sys.stderr.isatty() else None,
    )
