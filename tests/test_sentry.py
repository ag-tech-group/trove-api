"""Tests for Sentry initialization and PII scrubbing in app/sentry.py."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings
from app.sentry import _scrub_pii, init_sentry

DSN = "https://public@o0.ingest.sentry.io/0"


def _settings(**overrides) -> Settings:
    return Settings(environment="development", **overrides)


class TestInit:
    def test_empty_dsn_initialises_nothing(self):
        """An empty DSN is a total no-op, not a degraded init.

        Development and tests run without a Sentry project, and production
        stays Sentry-less until the DSN is bound rather than failing to start.
        """
        with (
            patch("app.sentry.settings", _settings(sentry_dsn="")),
            patch("app.sentry.sentry_sdk.init") as mock_init,
            patch("app.sentry.ignore_logger") as mock_ignore,
        ):
            init_sentry()

        mock_init.assert_not_called()
        mock_ignore.assert_not_called()

    def test_dsn_initialises_the_sdk(self):
        with (
            patch("app.sentry.settings", _settings(sentry_dsn=DSN)),
            patch("app.sentry.sentry_sdk.init") as mock_init,
            patch("app.sentry.ignore_logger"),
        ):
            init_sentry()

        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == DSN
        assert kwargs["environment"] == "development"
        assert kwargs["send_default_pii"] is False
        assert kwargs["traces_sample_rate"] == 0.0

    def test_ignores_the_security_logger(self):
        """`trove.security` must never reach Sentry, as an event or a breadcrumb.

        It logs every auth event at INFO with email, IP, user agent and user ID.
        The SDK captures INFO as breadcrumbs by default and breadcrumbs attach
        to whatever error is captured next, so without this an unrelated 500
        would arrive carrying a trail of addresses from unrelated sessions.
        """
        with (
            patch("app.sentry.settings", _settings(sentry_dsn=DSN)),
            patch("app.sentry.sentry_sdk.init"),
            patch("app.sentry.ignore_logger") as mock_ignore,
        ):
            init_sentry()

        mock_ignore.assert_called_once_with("trove.security")

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [("", None), ("abc123", "abc123")],
    )
    def test_empty_release_is_sent_as_none(self, configured, expected):
        """A local build has no SHA, and "no release" is not a release named "".

        The release is baked into the image at build time, so an image built
        outside CI carries an empty value.
        """
        with (
            patch("app.sentry.settings", _settings(sentry_dsn=DSN, sentry_release=configured)),
            patch("app.sentry.sentry_sdk.init") as mock_init,
            patch("app.sentry.ignore_logger"),
        ):
            init_sentry()

        assert mock_init.call_args.kwargs["release"] == expected


class TestScrubbing:
    @pytest.mark.parametrize(
        "key",
        ["password", "access_token", "client_secret", "authorization", "api_key", "credential"],
    )
    def test_redacts_credential_keys(self, key):
        assert _scrub_pii({key: "sensitive"}, {})[key] == "[REDACTED]"

    @pytest.mark.parametrize("key", ["email", "database_url"])
    def test_redacts_keys_the_log_pattern_allows(self, key):
        """Sentry's pattern is deliberately stricter than the logging one.

        Cloud Logging is inside the project and governed by project IAM; Sentry
        is a third party. `email` is logged on purpose by the security audit
        trail and still must not be exported — it reaches events through
        fastapi-users request context even though that logger is ignored.
        """
        assert _scrub_pii({key: "value"}, {})[key] == "[REDACTED]"

    def test_recurses_into_nested_structures(self):
        """Sentry events nest arbitrarily, so a fixed set of paths would miss most of it."""
        event = {
            "request": {"headers": {"authorization": "Bearer xyz"}},
            "breadcrumbs": [{"data": {"password": "hunter2"}}],
        }

        result = _scrub_pii(event, {})

        assert result["request"]["headers"]["authorization"] == "[REDACTED]"
        assert result["breadcrumbs"][0]["data"]["password"] == "[REDACTED]"

    def test_preserves_operational_context(self):
        """Over-scrubbing costs debuggability, so non-credential keys survive."""
        event = {"user_id": "u-1", "ip": "10.0.0.1", "authorization_id": "auth-42"}

        assert _scrub_pii(event, {}) == event


def test_init_sentry_is_called_before_the_app_is_constructed():
    """Guards the one ordering constraint whose breakage is silent.

    The SDK's Starlette and FastAPI integrations auto-instrument the middleware
    stack at app construction time, so initialising after `FastAPI(...)` loses
    request context on every captured event. Nothing raises and events still
    arrive, so no other test would notice.
    """
    source = (Path(__file__).parent.parent / "app" / "main.py").read_text()

    # Anchored to line starts so the prose in main.py's own comment, which
    # quotes both of these, cannot satisfy the assertion instead of the code.
    init = re.search(r"^init_sentry\(\)", source, re.MULTILINE)
    construction = re.search(r"^app = FastAPI\(", source, re.MULTILINE)

    assert init is not None, "init_sentry() is no longer called at module level in app/main.py"
    assert construction is not None, "app = FastAPI( is no longer at module level in app/main.py"
    assert init.start() < construction.start(), (
        "init_sentry() must be called before the FastAPI app is constructed"
    )
