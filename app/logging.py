"""Structured logging configuration using structlog.

Output is JSON in production so Cloud Logging parses each line into fields
rather than storing it as opaque text, and a human-readable console renderer
in development.

`setup_logging()` installs a single root handler, so stdlib loggers — including
`trove.security` in `app/auth/security_logging.py` and anything a dependency
emits — flow through the same processor chain and land in the same format.
"""

import logging
import re
import sys
from typing import Any

import structlog

from app.config import settings

# Keys whose values are redacted from log output.
#
# `authorization` carries a WORD BOUNDARY; the others deliberately do not.
# Substring matching is correct for `token` and `secret`, whose compounds are
# exactly what must be scrubbed — `access_token`, `refresh_token`, `secret_key`,
# `client_secret`. It is wrong for `authorization`, whose compounds are
# identifiers and permission names rather than credentials, so redacting them
# destroys the values an operator needs while protecting nothing. A bare
# `authorization` key — an actual header value — still matches.
#
# This pattern covers credentials only. `app/sentry.py` composes a stricter one
# for events leaving the project, and the asymmetry is deliberate: see the note
# there.
PII_KEY_PATTERN = re.compile(
    r"(password|token|secret|\bauthorization\b|cookie|api_key|credential)",
    re.IGNORECASE,
)

# Cloud Logging reads the level from `severity`, not `level`, and expects its
# own names. Without this a JSON line is ingested but every entry renders at
# default severity, so filtering by error in the console returns nothing.
_LEVEL_TO_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
}


def pii_scrubbing_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact values for keys that look like they contain sensitive data."""
    for key in list(event_dict):
        if PII_KEY_PATTERN.search(key):
            event_dict[key] = "[REDACTED]"
    return event_dict


def gcp_severity_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Rename `level` to `severity` with Cloud Logging-compatible values."""
    level = event_dict.pop("level", None)
    if level:
        event_dict["severity"] = _LEVEL_TO_SEVERITY.get(level, level.upper())
    return event_dict


def setup_logging() -> None:
    """Configure structlog. Call once, before the FastAPI app is constructed."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Copies a stdlib record's `extra` dict into the event dict. A no-op on
        # records that originate in structlog, so one chain serves both — but
        # required for `app/auth/security_logging.py`, which logs through stdlib
        # and passes everything it records in `extra`. Ordered ahead of the
        # scrubber so those fields are scrubbed rather than passed through.
        structlog.stdlib.ExtraAdder(),
        pii_scrubbing_processor,
    ]

    if settings.is_development:
        # Colors gated on isatty rather than left at ConsoleRenderer's
        # unconditional default, so a non-tty sink never receives ANSI escapes.
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty()
        )
    else:
        renderer = structlog.processors.JSONRenderer()
        shared_processors.append(gcp_severity_processor)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # Applies the chain above to records that did NOT come from structlog.
        # Without it a stdlib record renders as a bare `event` string with no
        # timestamp, level, logger name or severity, and never passes through
        # the PII scrubber. `trove.security` is stdlib, so that is not an edge
        # case here — it is the audit trail.
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())

    # Quiet noisy loggers. uvicorn.access duplicates information Cloud Run's own
    # request logs already carry, and httpx logs an INFO line per outbound call.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)
