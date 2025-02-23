"""Provides logging utilities."""

import logging
import typing as _t

from msgspec import json
import structlog
from that_depends import Provide, inject

from plugboard.utils.di import DI
from plugboard.utils.settings import Settings


def _serialiser(obj: _t.Any, default: _t.Callable | None) -> bytes:
    return json.encode(obj)


@inject
def configure_logging(settings: Settings = Provide[DI.settings]) -> None:
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
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=processors,  # type: ignore[arg-type]
        # Use BytesLoggerFactory when using msgspec serialization to bytes
        logger_factory=structlog.BytesLoggerFactory() if settings.log_structured else None,
    )
