"""Transactional email, sent through Resend.

THE PROVIDER IS NOT CHOSEN HERE. trove-infra's foundation root declares the DKIM
key and the return-path CNAMEs that let Resend sign and send as
mail.trovebox.io; those records name the provider, and a receiver checks a
message against them. So this module's job is narrow: post to the API that the
DNS already authorises, as the sender those records cover.

NO PROVIDER SDK. Sending is one JSON POST to a single endpoint, and httpx is
already here — `httpx-oauth` brings it and the Google OAuth flow uses it — so an
SDK would add a dependency to save a dictionary literal. `app/storage.py`
documents the other half of the trade: its client is synchronous, so every call
there has to cross `asyncio.to_thread` to keep the event loop free. An async
client is available for this one, so the send is simply awaited.

AN EMPTY API KEY DOES NOT SEND AND DOES NOT RAISE, the same contract
`app/sentry.py` gives an empty DSN. The reason is deployment ordering and it is
not hypothetical: Cloud Run resolves a `secret_key_ref` when it builds a
revision, so `RESEND_API_KEY` cannot be bound to the service until its Secret
Manager container has a payload. A key the application demanded at startup would
therefore fail the first revision that carried this code. What an unconfigured
key does instead depends on the environment — see `_log_unsent`, where the
asymmetry is the security-relevant part of this file.
"""

import logging
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.email_templates import RenderedEmail, email_verification, password_reset

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

# EXPLICIT, BECAUSE THIS CALL IS AWAITED INSIDE A REQUEST. `fastapi-users` fires
# its hooks inline, so the client waiting on POST /auth/forgot-password waits on
# this too. A provider that accepts the connection and then stalls would
# otherwise hold the request for httpx's default, and the ceiling wants to be a
# decision rather than a default.
_TIMEOUT = httpx.Timeout(10.0)


class EmailSendError(Exception):
    """A message was not accepted by the provider.

    Raised rather than swallowed so the decision about what a send failure means
    belongs to the caller. `app/auth/users.py` is where that policy lives, and
    it explains why the auth hooks answer this by logging.
    """


async def send_password_reset_email(to: str, token: str, *, expires_in_seconds: int) -> None:
    """Send the password reset link for `token` to `to`.

    The lifetime is a parameter rather than a constant because the copy states
    it: the caller passes its user manager's own
    `reset_password_token_lifetime_seconds`, which is the value the token was
    actually minted with, so the sentence in the email cannot drift away from
    when the link stops working.
    """
    await _send(
        to,
        password_reset(
            url=_frontend_link("/reset-password", token),
            expires_in_seconds=expires_in_seconds,
        ),
    )


async def send_verification_email(to: str, token: str, *, expires_in_seconds: int) -> None:
    """Send the address-confirmation link for `token` to `to`."""
    await _send(
        to,
        email_verification(
            url=_frontend_link("/verify-email", token),
            expires_in_seconds=expires_in_seconds,
        ),
    )


def _frontend_link(path: str, token: str) -> str:
    """Build the link a message points at.

    IT LANDS IN trove-web, NOT IN THIS API, and that is the shape of both flows:
    the token identifies a form the person still has to fill in — a new password,
    or just a confirmation — and the browser posts it back to `/auth/*` from
    there. A link straight to an API endpoint would be a GET that mutates.

    `frontend_url` carries no trailing slash; `app/config.py`'s default and the
    deployed value agree on that, so the leading slash on `path` is the only
    separator. `urlencode` rather than interpolation so a token containing a
    character that means something in a query string cannot break the link.
    """
    return f"{settings.frontend_url}{path}?{urlencode({'token': token})}"


async def _send(to: str, message: RenderedEmail) -> None:
    """Hand one rendered message to Resend. Raises `EmailSendError` if refused."""
    if not settings.resend_api_key:
        _log_unsent(to=to, message=message)
        return

    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
    }

    try:
        # A CLIENT PER CALL, not one shared at module scope. The volume is
        # password resets, so the handshake this repeats is not worth optimising
        # away — and a long-lived AsyncClient pins its connection pool to the
        # event loop that first used it, which under `asyncio_mode = "auto"` is a
        # fresh loop for every single test. Pooling would buy microseconds and
        # cost a class of cross-loop failure that only appears in the suite.
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise EmailSendError(f"Email transport to Resend failed: {exc}") from exc

    if response.is_error:
        # The response body is the only thing that makes a refusal diagnosable —
        # an unverified sending domain and a malformed From address are both
        # 4xx with the reason in the body, and are otherwise indistinguishable.
        # It carries no credential; the API key travels in the request.
        raise EmailSendError(
            f"Resend refused the message with {response.status_code}: {response.text}"
        )

    logger.info("Sent %r to %s", message.subject, to)


def _log_unsent(*, to: str, message: RenderedEmail) -> None:
    """Record a message that no API key was configured to send.

    THE BODY IS LOGGED IN DEVELOPMENT ONLY, AND THE ASYMMETRY IS THE POINT.

    Locally it is the feature. A reset link on stdout completes the whole flow
    with no Resend account, no verified domain and no real inbox to receive at,
    which is what makes the endpoint testable by hand at all.

    Anywhere else it would be a vulnerability. The link IS the credential — a
    valid password reset token for a named account — so writing it to Cloud
    Logging grants a password reset to everyone holding log access, for the
    token's whole lifetime and for as long as the log is retained. So outside
    development this records only that a send was skipped, and records it at
    ERROR: an unconfigured key means password resets are silently not arriving,
    which is an operator's problem to find out about immediately rather than
    from a support request.
    """
    if settings.is_development:
        logger.warning(
            "RESEND_API_KEY is empty — nothing was sent. The message follows so the "
            "flow can be completed by hand.\nTo: %s\nSubject: %s\n\n%s",
            to,
            message.subject,
            message.text,
        )
    else:
        logger.error(
            "RESEND_API_KEY is empty — no email was sent to %s (%r). Bind the Resend "
            "secret to the service; until then every password reset silently fails.",
            to,
            message.subject,
        )
