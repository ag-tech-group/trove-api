"""End-to-end tests for the password reset and email verification flows.

These exercise the routes mounted in app/main.py rather than the email module,
which tests/test_email.py covers. `app.auth.users.send_password_reset_email` is
patched here to capture the token the manager minted, which is also the only way
to get a real one — the API never returns it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email import EmailSendError
from app.models.refresh_token import RefreshToken
from app.models.user import User


class Outbox:
    """Records the calls a hook made to the email layer."""

    def __init__(self):
        self.sent: list[tuple[str, str, int]] = []
        self.raises: Exception | None = None

    async def __call__(self, to: str, token: str, *, expires_in_seconds: int) -> None:
        self.sent.append((to, token, expires_in_seconds))
        if self.raises is not None:
            raise self.raises

    @property
    def only(self) -> tuple[str, str, int]:
        assert len(self.sent) == 1, f"expected one email, got {len(self.sent)}"
        return self.sent[0]


@pytest.fixture
def outbox():
    box = Outbox()
    with patch("app.auth.users.send_password_reset_email", box):
        yield box


@pytest.fixture
def verify_outbox():
    box = Outbox()
    with patch("app.auth.users.send_verification_email", box):
        yield box


async def _forgot(client: AsyncClient, email: str):
    return await client.post("/auth/forgot-password", json={"email": email})


class TestForgotPassword:
    async def test_known_address_is_emailed_a_reset_link(
        self, client: AsyncClient, test_user: User, outbox: Outbox
    ):
        response = await _forgot(client, test_user.email)

        assert response.status_code == 202
        to, token, lifetime = outbox.only
        assert to == test_user.email
        assert token, "the hook receives the minted reset token"
        assert lifetime == 3600, "the manager's own lifetime, so the copy cannot drift"

    async def test_unknown_address_gets_the_same_answer_and_no_email(
        self, client: AsyncClient, test_user: User, outbox: Outbox
    ):
        """THE ENUMERATION PROPERTY. The two answers must be indistinguishable,
        or the endpoint becomes a way to ask whether a given person has a Trove
        account.
        """
        unknown = await _forgot(client, "nobody@example.com")
        known = await _forgot(client, test_user.email)

        assert unknown.status_code == known.status_code == 202
        assert unknown.content == known.content
        assert [to for to, _, _ in outbox.sent] == [test_user.email], (
            "only the registered address is emailed, and the response does not say so"
        )

    async def test_inactive_account_is_not_emailed(
        self, client: AsyncClient, session: AsyncSession, outbox: Outbox
    ):
        """Still 202: a deactivated account must not be distinguishable either."""
        user = User(
            id=str(uuid.uuid4()),
            email="inactive@example.com",
            hashed_password="fakehash",
            is_active=False,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.commit()

        response = await _forgot(client, "inactive@example.com")

        assert response.status_code == 202
        assert outbox.sent == []

    async def test_a_send_failure_does_not_change_the_response(
        self, client: AsyncClient, test_user: User, outbox: Outbox
    ):
        """A provider outage must not become an enumeration oracle.

        If a failed send produced a 500, then during an outage an unregistered
        address would answer 202 and a registered one 500 — which is precisely
        the distinction the flat 202 exists to withhold.
        """
        outbox.raises = EmailSendError("Resend refused the message with 503")

        response = await _forgot(client, test_user.email)

        assert response.status_code == 202

    async def test_the_failure_is_logged_for_the_operator(
        self, client: AsyncClient, test_user: User, outbox: Outbox, caplog
    ):
        """Swallowed for the caller, not swallowed outright.

        ERROR is what the Sentry logging integration turns into an event, so the
        person who cannot be told is traded for the operator who can.
        """
        outbox.raises = EmailSendError("Resend refused the message with 503")

        with caplog.at_level("ERROR", logger="app.auth.users"):
            await _forgot(client, test_user.email)

        assert any("password reset" in r.getMessage() for r in caplog.records)


class TestResetPassword:
    async def _token_for(self, client: AsyncClient, outbox: Outbox, email: str) -> str:
        await _forgot(client, email)
        return outbox.only[1]

    async def test_a_valid_token_sets_the_new_password(
        self, client: AsyncClient, session: AsyncSession, test_user: User, outbox: Outbox
    ):
        token = await self._token_for(client, outbox, test_user.email)

        response = await client.post(
            "/auth/reset-password",
            json={"token": token, "password": "a-brand-new-password"},
        )

        assert response.status_code == 200
        # `.unique()` because User.oauth_accounts is lazy="joined" — SQLAlchemy
        # refuses scalar_one() on a result carrying a joined eager load.
        refreshed = (
            (await session.execute(select(User).where(User.email == test_user.email)))
            .unique()
            .scalar_one()
        )
        assert refreshed.hashed_password != "fakehash"

    async def test_a_token_cannot_be_used_twice(
        self, client: AsyncClient, test_user: User, outbox: Outbox
    ):
        """Single use falls out of the design rather than a nonce table.

        The token carries a fingerprint of the password hash it was minted
        against, and the reset replaces that hash — so the fingerprint stops
        matching the moment the first reset succeeds.
        """
        token = await self._token_for(client, outbox, test_user.email)
        first = await client.post(
            "/auth/reset-password", json={"token": token, "password": "pw-one"}
        )
        assert first.status_code == 200

        second = await client.post(
            "/auth/reset-password", json={"token": token, "password": "pw-two"}
        )

        assert second.status_code == 400
        assert second.json()["detail"] == "RESET_PASSWORD_BAD_TOKEN"

    async def test_a_garbage_token_is_rejected(self, client: AsyncClient, test_user: User):
        response = await client.post(
            "/auth/reset-password", json={"token": "not-a-jwt", "password": "whatever-goes"}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "RESET_PASSWORD_BAD_TOKEN"

    async def test_reset_revokes_every_refresh_token_family(
        self, client: AsyncClient, session: AsyncSession, test_user: User, outbox: Outbox
    ):
        """A RESET THAT LEAVES OLD SESSIONS ALIVE HAS NOT RECOVERED THE ACCOUNT.

        The usual reason to reset a password is that somebody else has it.
        Access tokens are 15-minute JWTs and cannot be revoked, but a session
        only outlives them by exchanging a refresh cookie against one of these
        rows — so revoking the families is the step that ends the intruder's
        access, and it caps their remaining window at one access token lifetime
        instead of the refresh token's week.
        """
        for family in ("laptop", "phone"):
            session.add(
                RefreshToken(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(str(test_user.id)),
                    token_family=family,
                    is_revoked=False,
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
            )
        await session.commit()

        token = await self._token_for(client, outbox, test_user.email)
        response = await client.post(
            "/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}
        )
        assert response.status_code == 200

        rows = (
            (
                await session.execute(
                    select(RefreshToken).where(RefreshToken.token_family.in_(("laptop", "phone")))
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert all(row.is_revoked for row in rows), "both sessions must be dead"

    async def test_another_users_sessions_are_untouched(
        self,
        client: AsyncClient,
        session: AsyncSession,
        test_user: User,
        other_user: User,
        outbox: Outbox,
    ):
        """Revocation is scoped by user_id, like every other query in this app."""
        session.add(
            RefreshToken(
                id=uuid.uuid4(),
                user_id=uuid.UUID(str(other_user.id)),
                token_family="bystander",
                is_revoked=False,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await session.commit()

        token = await self._token_for(client, outbox, test_user.email)
        await client.post(
            "/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}
        )

        bystander = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_family == "bystander")
            )
        ).scalar_one()
        assert bystander.is_revoked is False


class TestEmailVerification:
    async def test_requesting_verification_emails_a_token(
        self, client: AsyncClient, session: AsyncSession, verify_outbox: Outbox
    ):
        user = User(
            id=str(uuid.uuid4()),
            email="unverified@example.com",
            hashed_password="fakehash",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()

        response = await client.post(
            "/auth/request-verify-token", json={"email": "unverified@example.com"}
        )

        assert response.status_code == 202
        to, token, lifetime = verify_outbox.only
        assert to == "unverified@example.com"
        assert token
        assert lifetime == 3600

    async def test_unknown_address_gets_the_same_answer(
        self, client: AsyncClient, verify_outbox: Outbox
    ):
        response = await client.post(
            "/auth/request-verify-token", json={"email": "nobody@example.com"}
        )

        assert response.status_code == 202
        assert verify_outbox.sent == []

    async def test_a_valid_token_marks_the_account_verified(
        self, client: AsyncClient, session: AsyncSession, verify_outbox: Outbox
    ):
        user = User(
            id=str(uuid.uuid4()),
            email="unverified@example.com",
            hashed_password="fakehash",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()
        await client.post("/auth/request-verify-token", json={"email": "unverified@example.com"})
        token = verify_outbox.only[1]

        response = await client.post("/auth/verify", json={"token": token})

        assert response.status_code == 200
        assert response.json()["is_verified"] is True

    async def test_verification_is_offered_not_required(self, client: AsyncClient, test_user: User):
        """Nothing in the API checks `is_verified`.

        Mounting the verify router did not gate access on it, so accounts that
        registered before these routes existed are unaffected. Turning it on is
        a product decision, not a side effect of shipping the email service.
        """
        from app.auth import current_active_user
        from app.main import app

        unverified = User(
            id=str(uuid.uuid4()),
            email="u@example.com",
            hashed_password="fakehash",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        app.dependency_overrides[current_active_user] = lambda: unverified
        try:
            response = await client.get("/auth/me")
        finally:
            del app.dependency_overrides[current_active_user]

        assert response.status_code == 200


class TestRateLimits:
    async def test_forgot_password_is_capped_at_three_a_minute(
        self, client: AsyncClient, test_user: User, outbox: Outbox
    ):
        """The endpoint sends mail to an address the caller names.

        Uncapped it is a way to flood a stranger's inbox from Trove's sending
        domain, which spends the domain reputation the DKIM records in
        trove-infra exist to build — and its flat 202 also makes it the natural
        place to probe for who has an account.
        """
        for _ in range(3):
            assert (await _forgot(client, test_user.email)).status_code == 202

        fourth = await _forgot(client, test_user.email)

        assert fourth.status_code == 429
        assert len(outbox.sent) == 3, "the limit is reached before the send, not after"

    async def test_reset_password_is_capped(self, client: AsyncClient):
        for _ in range(5):
            response = await client.post(
                "/auth/reset-password", json={"token": "bad", "password": "irrelevant"}
            )
            assert response.status_code == 400

        assert (
            await client.post(
                "/auth/reset-password", json={"token": "bad", "password": "irrelevant"}
            )
        ).status_code == 429
