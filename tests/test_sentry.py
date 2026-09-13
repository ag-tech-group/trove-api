"""Tests for Sentry initialization and PII scrubbing in app/sentry.py."""

import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.auth.users import UserManager
from app.config import Settings
from app.email import send_password_reset_email
from app.sentry import _scrub_pii, init_sentry

DSN = "https://public@o0.ingest.sentry.io/0"
ADDRESS = "someone@example.com"
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1LTEifQ.c2lnbmF0dXJl"

# Bound before anything patches it, for the reason given in tests/test_email.py.
_RealAsyncClient = httpx.AsyncClient


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

    def test_local_variables_are_not_captured(self):
        """Frame locals hold values under arbitrary names, so they are left out, not filtered."""
        with (
            patch("app.sentry.settings", _settings(sentry_dsn=DSN)),
            patch("app.sentry.sentry_sdk.init") as mock_init,
            patch("app.sentry.ignore_logger"),
        ):
            init_sentry()

        assert mock_init.call_args.kwargs["include_local_variables"] is False

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

    def test_redacts_an_address_formatted_into_text(self):
        """No key can flag an address that has already become part of a sentence."""
        event = {"logentry": {"formatted": f"no email was sent to {ADDRESS} today"}}

        result = _scrub_pii(event, {})

        assert result["logentry"]["formatted"] == "no email was sent to [REDACTED] today"

    def test_redacts_an_address_under_a_key_that_names_nothing(self):
        """The login form sends the address as `username`, and request bodies are attached."""
        event = {"request": {"data": {"username": ADDRESS, "scope": ""}}}

        result = _scrub_pii(event, {})

        assert result["request"]["data"] == {"username": "[REDACTED]", "scope": ""}

    def test_redacts_a_jwt_wherever_it_is_embedded(self):
        """Every token this service issues is a JWT, so the shape is the signal."""
        event = {"exception": {"values": [{"value": f"bad link /reset-password#token={TOKEN}"}]}}

        result = _scrub_pii(event, {})

        assert result["exception"]["values"][0]["value"] == (
            "bad link /reset-password#token=[REDACTED]"
        )


class _Capture(Transport):
    """Keeps events in memory rather than sending them anywhere."""

    def __init__(self):
        super().__init__()
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        self.events.extend(item.payload.json for item in envelope.items if item.type == "event")


@pytest.fixture
def sentry_events():
    """The real SDK, initialised by the real `init_sentry()`, capturing events in memory."""
    capture = _Capture()
    real_init = sentry_sdk.init

    def init_into_memory(**options):
        # Auto-enabling integrations would patch Starlette and FastAPI beyond this fixture.
        return real_init(transport=capture, auto_enabling_integrations=False, **options)

    with (
        patch("app.sentry.settings", _settings(sentry_dsn=DSN)),
        patch("app.sentry.sentry_sdk.init", init_into_memory),
    ):
        init_sentry()
    sentry_sdk.get_isolation_scope().clear_breadcrumbs()

    try:
        yield capture.events
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)


@contextmanager
def _resend(handler):
    """Stand in for the provider, with real httpx building the request."""

    def factory(**kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    with (
        patch("app.email.settings", _settings(resend_api_key="re_test_key")),
        patch("app.email.httpx.AsyncClient", factory),
    ):
        yield


class TestWhatReachesSentry:
    async def test_a_failed_auth_email_is_reported_without_token_or_recipient(self, sentry_events):
        """Raised inside the send, whose frames held the token and the address."""

        def outage(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated outage", request=request)

        user = SimpleNamespace(id="u-1", email=ADDRESS)
        with _resend(outage):
            await UserManager(MagicMock()).on_after_forgot_password(user, TOKEN)

        assert len(sentry_events) == 1, "the failure must still be reported"
        sent = json.dumps(sentry_events)
        assert TOKEN not in sent
        assert ADDRESS not in sent

    async def test_an_unsendable_email_is_reported_without_recipient(self, sentry_events):
        """`RESEND_API_KEY` unset outside development: reported, recipient withheld."""
        production = Settings(
            environment="production",
            resend_api_key="",
            secret_key="s" * 32,
            database_url="postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
            storage_bucket_name="trove-images",
        )

        with patch("app.email.settings", production):
            await send_password_reset_email(ADDRESS, TOKEN, expires_in_seconds=3600)

        assert len(sentry_events) == 1
        assert ADDRESS not in json.dumps(sentry_events)

    async def test_a_sent_email_leaves_no_recipient_in_later_breadcrumbs(
        self, sentry_events, caplog
    ):
        """A breadcrumb rides along on whatever error comes next in the same scope."""

        def accept(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "msg_1"})

        with _resend(accept), caplog.at_level(logging.INFO, logger="app.email"):
            await send_password_reset_email(ADDRESS, TOKEN, expires_in_seconds=3600)
        logging.getLogger("app.unrelated").error("a later failure")

        assert len(sentry_events) == 1
        assert sentry_events[0]["breadcrumbs"]["values"], "the send left no breadcrumb to check"
        assert ADDRESS not in json.dumps(sentry_events)


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
