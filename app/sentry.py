"""Sentry SDK initialization.

`init_sentry()` must be called *before* the FastAPI app is constructed. The
SDK's Starlette and FastAPI integrations auto-instrument the middleware stack at
app construction time, so a late init silently loses request context on every
captured event — the app still starts and events still arrive, just without the
URL, method or headers that make them actionable.

An empty `SENTRY_DSN` is a total no-op. Development and tests need no Sentry
project, and production stays Sentry-less until the DSN is bound rather than
failing to start.
"""

import re
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger

from app.config import settings
from app.logging import PII_KEY_PATTERN

# Deliberately stricter than the logging pattern it extends.
#
# Cloud Logging is inside the project and governed by project IAM; Sentry is a
# third party. So keys that are legitimate to log are not automatically
# legitimate to export, and the two sinks get two patterns rather than one.
#
# `email` is the case that drives this. `app/auth/security_logging.py` records it
# on purpose — an auth audit trail without the account is not an audit trail —
# and that logger never reaches Sentry at all (see `_IGNORED_LOGGERS`). It is
# scrubbed here anyway because it also arrives through `fastapi-users` request
# context, and the cost of over-scrubbing one field is zero.
SENTRY_PII_KEY_PATTERN = re.compile(
    rf"{PII_KEY_PATTERN.pattern}|email|database_url",
    re.IGNORECASE,
)

# Loggers whose records must never become Sentry events or breadcrumbs.
#
# `trove.security` logs every auth event at INFO with `email`, `ip`,
# `user_agent` and `user_id` in `extra`. The SDK's LoggingIntegration defaults to
# capturing INFO as breadcrumbs, and breadcrumbs attach to whatever error is
# captured next — so without this an unrelated 500 would arrive carrying a trail
# of addresses and IPs from unrelated sessions.
#
# Ignored wholesale rather than scrubbed field by field: these events belong in
# Cloud Logging, where they already are. There is no version of this where
# shipping them to a third party is the goal, so filtering fields would be
# solving a problem that should not exist.
_IGNORED_LOGGERS = ("trove.security",)


def _scrub_pii(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Recursively redact PII-like keys anywhere in a Sentry event.

    Sentry events nest dicts and lists arbitrarily — tags, extra,
    request.headers, request.cookies, breadcrumbs, exception values — so the
    scrubber walks the whole tree rather than a fixed set of paths. A key whose
    name matches has its value replaced with `[REDACTED]`; recursion continues
    into non-matching keys' values.
    """

    def _scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: "[REDACTED]" if SENTRY_PII_KEY_PATTERN.search(str(k)) else _scrub(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_scrub(item) for item in obj]
        return obj

    return _scrub(event)


def init_sentry() -> None:
    """Initialize the Sentry SDK. No-op when `SENTRY_DSN` is empty.

    Errors only to start. `traces_sample_rate=0.0` because tracing draws on a
    separate quota the free plan allocates sparingly and there is no outstanding
    performance question — turning it on later is an env var change, not a code
    change.

    `send_default_pii=False` is the SDK default, set explicitly so the intent is
    visible next to the scrubber that backs it up.
    """
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # `or None` rather than the empty string, which would create a release
        # literally named empty. None hands off to the SDK's own detection,
        # which reads the git SHA when a repo is present — useful when
        # verifying locally, and inert in the container, which has no .git.
        release=settings.sentry_release or None,
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=_scrub_pii,
    )

    for logger_name in _IGNORED_LOGGERS:
        ignore_logger(logger_name)
