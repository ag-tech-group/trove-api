"""Signing in through an OAuth provider that links accounts by email."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import UserManager
from app.models.oauth_account import OAuthAccount
from app.models.refresh_token import RefreshToken
from app.models.user import User

EMAIL = "collector@example.com"
PASSWORD = "the-original-password"
GOOGLE_ID = "google-account-123"


@pytest.fixture
def manager(session: AsyncSession) -> UserManager:
    return UserManager(SQLAlchemyUserDatabase(session, User, OAuthAccount))


async def _account(session: AsyncSession, manager: UserManager, *, verified: bool) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=EMAIL,
        hashed_password=manager.password_helper.hash(PASSWORD),
        is_active=True,
        is_superuser=False,
        is_verified=verified,
    )
    session.add(user)
    await session.commit()
    return user


async def _session_for(session: AsyncSession, user: User, family: str) -> None:
    session.add(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=uuid.UUID(str(user.id)),
            token_family=family,
            is_revoked=False,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await session.commit()


async def _google_sign_in(manager: UserManager, email: str = EMAIL) -> User:
    # The arguments app/auth/oauth.py passes.
    return await manager.oauth_callback(
        "google",
        "google-access-token",
        GOOGLE_ID,
        email,
        associate_by_email=True,
        is_verified_by_default=True,
    )


def _password_works(manager: UserManager, user: User) -> bool:
    verified, _ = manager.password_helper.verify_and_update(PASSWORD, user.hashed_password)
    return verified


async def _revoked(session: AsyncSession, family: str) -> bool:
    row = await session.execute(select(RefreshToken).where(RefreshToken.token_family == family))
    return row.scalar_one().is_revoked


async def test_linking_verifies_an_unverified_account_and_retires_its_credentials(
    session: AsyncSession, manager: UserManager
):
    account = await _account(session, manager, verified=False)
    await _session_for(session, account, "laptop")

    user = await _google_sign_in(manager)

    assert str(user.id) == str(account.id)
    assert user.is_verified
    assert not _password_works(manager, user)
    assert await _revoked(session, "laptop")
    assert [a.account_id for a in user.oauth_accounts] == [GOOGLE_ID]


async def test_linking_a_verified_account_leaves_its_password_and_sessions(
    session: AsyncSession, manager: UserManager
):
    account = await _account(session, manager, verified=True)
    await _session_for(session, account, "laptop")

    user = await _google_sign_in(manager)

    assert str(user.id) == str(account.id)
    assert _password_works(manager, user)
    assert not await _revoked(session, "laptop")
    assert [a.account_id for a in user.oauth_accounts] == [GOOGLE_ID]


async def test_an_account_linked_while_unverified_is_verified_at_its_next_sign_in(
    session: AsyncSession, manager: UserManager
):
    account = await _account(session, manager, verified=False)
    session.add(
        OAuthAccount(
            oauth_name="google",
            access_token="old-access-token",
            account_id=GOOGLE_ID,
            account_email=EMAIL,
            user_id=account.id,
        )
    )
    await session.commit()

    user = await _google_sign_in(manager)

    assert user.is_verified
    assert not _password_works(manager, user)


async def test_a_new_google_user_is_created_verified(manager: UserManager):
    user = await _google_sign_in(manager, email="newcomer@example.com")

    assert user.email == "newcomer@example.com"
    assert user.is_verified
    assert [a.account_id for a in user.oauth_accounts] == [GOOGLE_ID]


async def test_other_users_sessions_are_untouched(
    session: AsyncSession, manager: UserManager, other_user: User
):
    await _account(session, manager, verified=False)
    await _session_for(session, other_user, "bystander")

    await _google_sign_in(manager)

    assert not await _revoked(session, "bystander")
