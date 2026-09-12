"""Tests for app/email.py and app/email_templates.py."""

import logging
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest

from app.config import Settings
from app.email import (
    RESEND_API_URL,
    EmailSendError,
    _frontend_link,
    send_password_reset_email,
    send_verification_email,
)
from app.email_templates import _humanize_seconds, email_verification, password_reset

KEY = "re_test_key"
TOKEN = "eyJhbGci.eyJzdWIi.c2ln"

# BOUND BEFORE ANYTHING PATCHES IT. `app.email.httpx` is the httpx module
# itself, so patching `app.email.httpx.AsyncClient` replaces the attribute
# globally rather than only inside app/email.py — and a factory that then
# referred to `httpx.AsyncClient` would call itself.
_RealAsyncClient = httpx.AsyncClient


def _settings(**overrides) -> Settings:
    defaults = {"environment": "development", "frontend_url": "https://trovebox.io"}
    return Settings(**{**defaults, **overrides})


class Resend:
    """A stand-in for Resend that records what was actually sent to it.

    ROUTES THROUGH REAL httpx VIA MockTransport rather than mocking the client.
    A mocked `AsyncClient` would let a malformed payload pass — the assertions
    would read back whatever was handed to the mock, not what would go on the
    wire. Here httpx builds the request for real, so the JSON body and the
    Authorization header under test are the ones a live send would produce.
    """

    def __init__(self, status: int = 200, body: dict | None = None):
        self.status = status
        self.body = body if body is not None else {"id": "msg_1"}
        self.requests: list[httpx.Request] = []
        self.raises: Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        return httpx.Response(self.status, json=self.body)

    @property
    def sent(self) -> dict:
        """The JSON body of the single request made."""
        assert len(self.requests) == 1, f"expected one send, got {len(self.requests)}"
        import json

        return json.loads(self.requests[0].content)


@contextmanager
def sending(resend: Resend, **setting_overrides):
    """Run the block with `resend` standing in for the provider."""

    def factory(**kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(resend), **kwargs)

    with (
        patch("app.email.settings", _settings(resend_api_key=KEY, **setting_overrides)),
        patch("app.email.httpx.AsyncClient", factory),
    ):
        yield resend


class TestHumanizeSeconds:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (3600, "1 hour"),
            (7200, "2 hours"),
            (1800, "30 minutes"),
            (60, "1 minute"),
            (90, "2 minutes"),
        ],
    )
    def test_renders_a_lifetime_as_copy(self, seconds, expected):
        assert _humanize_seconds(seconds) == expected


class TestTemplates:
    def test_reset_link_appears_in_both_body_parts(self):
        """A text alternative that omitted the link would be a dead email.

        Both parts go out on every message, so a client that renders text
        instead of HTML has to be able to complete the flow too.
        """
        url = "https://trovebox.io/reset-password?token=abc"

        message = password_reset(url=url, expires_in_seconds=3600)

        assert url in message.html
        assert url in message.text

    def test_copy_states_the_lifetime_it_was_given(self):
        """The expiry sentence is derived, never written twice.

        `app/auth/users.py` passes the user manager's own
        `reset_password_token_lifetime_seconds`, so changing the token lifetime
        changes this sentence. A hardcoded "1 hour" would quietly start lying.
        """
        hour = password_reset(url="https://x/y", expires_in_seconds=3600)
        half = password_reset(url="https://x/y", expires_in_seconds=1800)

        assert "1 hour" in hour.text
        assert "30 minutes" in half.text
        assert "1 hour" not in half.text

    def test_url_is_escaped_into_the_markup(self):
        """A raw `&` between query parameters would truncate the href.

        Only one parameter is sent today, so this guards the helper rather than
        a live bug — the moment a second one is added, an unescaped ampersand
        silently produces a link that drops the token.
        """
        url = "https://trovebox.io/reset-password?token=abc&next=%2Fitems"

        message = password_reset(url=url, expires_in_seconds=3600)

        assert "token=abc&amp;next=%2Fitems" in message.html
        assert "token=abc&next=" not in message.html
        assert url in message.text, "the text part is not markup and is not escaped"

    def test_reset_email_says_the_password_is_unchanged(self):
        """The recipient may be someone who did nothing.

        The address comes from an unauthenticated request, so this message
        reaches people who did not ask for it. For them the only useful content
        is that no action is required.
        """
        message = password_reset(url="https://x/y", expires_in_seconds=3600)

        assert "ignore this email" in message.text
        assert "will not change" in message.text

    def test_the_two_messages_are_distinguishable(self):
        reset = password_reset(url="https://x/y", expires_in_seconds=3600)
        verify = email_verification(url="https://x/y", expires_in_seconds=3600)

        assert reset.subject == "Reset your Trove password"
        assert verify.subject == "Verify your Trove email address"

    def test_no_oklch_reaches_a_mail_client(self):
        """trove-web's palette is oklch; mail clients do not implement it.

        The colours here are those same values converted to hex. An oklch()
        anywhere in the output means a colour was copied across rather than
        converted, and it renders as nothing at all in most clients.
        """
        message = password_reset(url="https://x/y", expires_in_seconds=3600)

        assert "oklch" not in message.html
        assert "#9c5f32" in message.html, "trove-web's --primary, converted"

    def test_styles_are_inline_rather_than_a_stylesheet(self):
        """Gmail strips `<style>` blocks, so a stylesheet would send unstyled mail."""
        message = password_reset(url="https://x/y", expires_in_seconds=3600)

        assert "<style" not in message.html
        assert 'style="' in message.html


class TestFrontendLink:
    def test_link_lands_in_the_frontend_not_the_api(self):
        """Both tokens name a form a person still has to fill in.

        The browser posts the token back to `/auth/*` from the frontend page, so
        a link straight at an API endpoint would make a GET that mutates.
        """
        with patch("app.email.settings", _settings()):
            link = _frontend_link("/reset-password", TOKEN)

        assert link.startswith("https://trovebox.io/reset-password?")
        assert "/auth/" not in link

    def test_token_is_query_encoded(self):
        """`urlencode`, not interpolation: a token is opaque to this module."""
        with patch("app.email.settings", _settings()):
            link = _frontend_link("/reset-password", "a b&c=d")

        assert link.endswith("?token=a+b%26c%3Dd")

    def test_no_double_slash_before_the_path(self):
        """`frontend_url` carries no trailing slash, deployed or defaulted.

        The same mismatch produced "...netlify.app//login" from the OAuth
        failure redirect before the trovebox.io cutover.
        """
        with patch("app.email.settings", _settings(frontend_url="https://trovebox.io")):
            assert "//reset-password" not in _frontend_link("/reset-password", TOKEN)


class TestSend:
    async def test_posts_the_message_to_resend(self):
        resend = Resend()

        with sending(resend):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        request = resend.requests[0]
        assert str(request.url) == RESEND_API_URL
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {KEY}"

        body = resend.sent
        assert body["to"] == ["a@b.com"]
        assert body["subject"] == "Reset your Trove password"
        assert body["from"] == "Trove <noreply@mail.trovebox.io>"
        assert TOKEN in body["html"]
        assert TOKEN in body["text"]

    async def test_every_message_carries_both_body_parts(self):
        """HTML-only mail scores worse with receivers for no gain."""
        resend = Resend()

        with sending(resend):
            await send_verification_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert resend.sent["html"].startswith("<!doctype html>")
        assert resend.sent["text"].strip()

    async def test_sender_is_configurable(self):
        resend = Resend()

        with sending(resend, email_from="Trove Dev <dev@example.test>"):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert resend.sent["from"] == "Trove Dev <dev@example.test>"

    async def test_refusal_raises_with_the_provider_reason(self):
        """The body is the only thing that distinguishes one 4xx from another.

        An unverified sending domain and a malformed From address are both a
        422 with the reason in the body and nothing else to tell them apart.
        """
        resend = Resend(status=422, body={"message": "The mail.trovebox.io domain is not verified"})

        with sending(resend), pytest.raises(EmailSendError, match="422"):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

    async def test_refusal_message_names_the_cause(self):
        resend = Resend(status=403, body={"message": "domain not verified"})

        with sending(resend):
            with pytest.raises(EmailSendError) as caught:
                await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert "domain not verified" in str(caught.value)

    async def test_transport_failure_raises_email_send_error(self):
        """Callers handle one exception type, not httpx's hierarchy."""
        resend = Resend()
        resend.raises = httpx.ConnectError("name resolution failed")

        with sending(resend), pytest.raises(EmailSendError, match="transport"):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)


class TestUnconfiguredKey:
    """An empty RESEND_API_KEY disables sending without failing startup.

    The same contract `app/sentry.py` gives an empty DSN, for a sharper reason:
    Cloud Run resolves a secret_key_ref when it builds a revision, so the key
    cannot be bound before its Secret Manager container has a payload. A
    required key would fail the first revision to carry this code.
    """

    async def test_nothing_is_sent(self):
        resend = Resend()

        def factory(**kwargs):
            return _RealAsyncClient(transport=httpx.MockTransport(resend), **kwargs)

        with (
            patch("app.email.settings", _settings(resend_api_key="")),
            patch("app.email.httpx.AsyncClient", factory),
        ):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert resend.requests == [], "no key must mean no call, not an unauthenticated one"

    async def test_development_logs_the_link_so_the_flow_can_be_walked(self, caplog):
        """Locally this substitution IS the feature.

        A reset link on stdout completes the whole flow with no Resend account,
        no verified domain and no real inbox to receive at.
        """
        with (
            patch("app.email.settings", _settings(resend_api_key="", environment="development")),
            caplog.at_level(logging.DEBUG, logger="app.email"),
        ):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert TOKEN in caplog.text
        assert "a@b.com" in caplog.text

    async def test_outside_development_the_link_is_never_logged(self, caplog):
        """THE SECURITY PROPERTY OF THIS MODULE.

        The link is a working password reset token for a named account. Writing
        it to Cloud Logging grants a password reset to everyone with log access,
        for the token's whole lifetime and the log's whole retention. So the
        body is logged in development and nowhere else.
        """
        production = _settings(
            resend_api_key="",
            environment="production",
            secret_key="s" * 32,
            database_url="postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
            storage_bucket_name="trove-images",
        )

        with (
            patch("app.email.settings", production),
            caplog.at_level(logging.DEBUG, logger="app.email"),
        ):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        assert TOKEN not in caplog.text
        assert "/reset-password" not in caplog.text

    async def test_outside_development_it_is_an_error_not_a_warning(self, caplog):
        """Silently not sending password resets is an operator's emergency.

        ERROR is what the Sentry logging integration captures as an event, so
        this surfaces as an alert rather than as a support request weeks later.
        """
        production = _settings(
            resend_api_key="",
            environment="production",
            secret_key="s" * 32,
            database_url="postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
            storage_bucket_name="trove-images",
        )

        with (
            patch("app.email.settings", production),
            caplog.at_level(logging.DEBUG, logger="app.email"),
        ):
            await send_password_reset_email("a@b.com", TOKEN, expires_in_seconds=3600)

        levels = {r.levelno for r in caplog.records if r.name == "app.email"}
        assert logging.ERROR in levels
