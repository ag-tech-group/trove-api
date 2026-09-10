"""Tests for the structlog processors in app/logging.py."""

import json
import logging
from unittest.mock import patch

import pytest
import structlog

from app.config import Settings
from app.logging import (
    PII_KEY_PATTERN,
    gcp_severity_processor,
    pii_scrubbing_processor,
    setup_logging,
)


class TestPiiScrubbing:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "access_token",
            "refresh_token",
            "client_secret",
            "secret_key",
            "authorization",
            "session_cookie",
            "api_key",
            "user_credential",
        ],
    )
    def test_redacts_credential_keys(self, key):
        result = pii_scrubbing_processor(None, "info", {"event": "req", key: "sensitive"})

        assert result[key] == "[REDACTED]"

    def test_preserves_authorization_compounds(self):
        """`authorization` matches on a word boundary, its compounds do not.

        Substring matching is right for `token` and `secret`, whose compounds
        are themselves credentials. It is wrong for `authorization`, whose
        compounds are identifiers and permission names — redacting those
        destroys values an operator needs while protecting nothing.
        """
        event = {"authorization": "Bearer xyz", "authorization_id": "auth-42"}

        result = pii_scrubbing_processor(None, "info", event)

        assert result["authorization"] == "[REDACTED]"
        assert result["authorization_id"] == "auth-42"

    def test_preserves_operational_keys(self):
        event = {"event": "request", "method": "GET", "path": "/items", "status_code": 200}

        assert pii_scrubbing_processor(None, "info", dict(event)) == event

    def test_matches_case_insensitively(self):
        event = {"Authorization": "Bearer xyz", "API_KEY": "key"}

        result = pii_scrubbing_processor(None, "info", event)

        assert result["Authorization"] == "[REDACTED]"
        assert result["API_KEY"] == "[REDACTED]"

    def test_does_not_redact_email(self):
        """Email is logged deliberately and scrubbed only on the way to Sentry.

        `app/auth/security_logging.py` records it because an auth audit trail
        without the account is not an audit trail. Cloud Logging is governed by
        project IAM; the stricter pattern lives in app/sentry.py.
        """
        assert not PII_KEY_PATTERN.search("email")


class TestGcpSeverity:
    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            ("debug", "DEBUG"),
            ("info", "INFO"),
            ("warning", "WARNING"),
            ("error", "ERROR"),
            ("critical", "CRITICAL"),
        ],
    )
    def test_maps_level_to_severity(self, level, expected):
        """Cloud Logging reads `severity`, not `level`, and ignores the latter.

        Without the rename every entry is ingested at default severity, so
        filtering by error in the console returns nothing.
        """
        result = gcp_severity_processor(None, level, {"event": "x", "level": level})

        assert result["severity"] == expected
        assert "level" not in result

    def test_leaves_events_without_a_level_alone(self):
        result = gcp_severity_processor(None, "info", {"event": "x"})

        assert "severity" not in result


@pytest.fixture
def isolated_logging():
    """Restore global logging and structlog state, which setup_logging() mutates."""
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    structlog.reset_defaults()


def test_stdlib_records_are_fully_rendered_and_scrubbed(capsys, isolated_logging):
    """Records from stdlib `logging` must get the same treatment as structlog's own.

    structlog.configure()'s processor chain applies only to records created
    through structlog. Stdlib records are "foreign" and reach the renderer
    through `foreign_pre_chain` instead — without it they render as a bare
    event string with no timestamp, level, logger or severity, and their
    `extra` dict never passes the PII scrubber.

    That is not an edge case here: `app/auth/security_logging.py` logs through
    stdlib and puts everything it records in `extra`, so it is the audit trail
    that would silently lose its fields.
    """
    production = Settings(
        environment="production",
        secret_key="s" * 32,
        database_url="postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
        storage_bucket_name="trove-images",
    )
    with patch("app.logging.settings", production):
        setup_logging()

    logging.getLogger("trove.security").info(
        "[LOGIN_SUCCESS]",
        extra={"security_event": "LOGIN_SUCCESS", "email": "a@b.com", "password": "hunter2"},
    )

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert payload["password"] == "[REDACTED]"
    assert payload["email"] == "a@b.com", "the audit trail keeps the account it is about"
    assert payload["security_event"] == "LOGIN_SUCCESS"
    assert payload["severity"] == "INFO"
    assert payload["logger"] == "trove.security"
    assert "timestamp" in payload
