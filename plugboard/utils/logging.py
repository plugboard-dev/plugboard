"""Provides logging utilities."""

import logging
import typing as _t

from msgspec import json
import structlog

from plugboard.utils.settings import Settings


def _is_ipython() -> bool:
    try:
        from builtins import get_ipython  # type: ignore [attr-defined]  # noqa: F401
    except ImportError:
        return False
    return True


def _serialiser(obj: _t.Any, default: _t.Callable | None) -> bytes:
    return json.encode(obj, enc_hook=default)


def configure_logging(settings: Settings) -> None:
    """Configures logging."""
    log_level = getattr(logging, settings.log_level)
    common_processors: _t.Iterable[structlog.typing.Processor] = [
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
        processors = list(common_processors) + [
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        processors = list(common_processors) + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=_serialiser),
        ]

    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=processors,
        # Use BytesLoggerFactory when using msgspec serialization to bytes
        logger_factory=structlog.BytesLoggerFactory()
        # See https://github.com/hynek/structlog/issues/417
        if settings.log_structured and not _is_ipython()
        else None,
    )
