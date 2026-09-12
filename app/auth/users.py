import logging
from collections.abc import AsyncGenerator, Awaitable
from uuid import UUID

from fastapi import Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import auth_backend
from app.auth.refresh import create_refresh_token, set_refresh_cookie
from app.auth.security_logging import SecurityEvent, log_security_event
from app.config import settings
from app.database import async_session_maker, get_async_session
from app.email import EmailSendError, send_password_reset_email, send_verification_email
from app.models.oauth_account import OAuthAccount
from app.models.refresh_token import RefreshToken
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def on_after_register(self, user: User, request: Request | None = None):
        log_security_event(
            SecurityEvent.REGISTER,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: Response | None = None,
    ):
        log_security_event(
            SecurityEvent.LOGIN_SUCCESS,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )
        if response is not None:
            async with async_session_maker() as session:
                refresh_jwt = await create_refresh_token(str(user.id), session)
                set_refresh_cookie(response, refresh_jwt)

    async def authenticate(
        self,
        credentials: OAuth2PasswordRequestForm,
    ) -> models.UP | None:
        user = await super().authenticate(credentials)
        if user is None:
            log_security_event(
                SecurityEvent.LOGIN_FAILURE,
                email=credentials.username,
                detail="invalid credentials",
            )
        return user

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ):
        log_security_event(
            SecurityEvent.PASSWORD_RESET_REQUESTED,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )
        await self._deliver(
            send_password_reset_email(
                user.email,
                token,
                # The manager's own attribute, so the "expires in ..." sentence in
                # the email is derived from the lifetime the token was actually
                # minted with and cannot drift away from it.
                expires_in_seconds=self.reset_password_token_lifetime_seconds,
            ),
            user=user,
            purpose="password reset",
        )

    async def on_after_reset_password(self, user: User, request: Request | None = None):
        log_security_event(
            SecurityEvent.PASSWORD_RESET_COMPLETED,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )
        await self._revoke_refresh_tokens(user)

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None):
        log_security_event(
            SecurityEvent.EMAIL_VERIFICATION_REQUESTED,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )
        await self._deliver(
            send_verification_email(
                user.email,
                token,
                expires_in_seconds=self.verification_token_lifetime_seconds,
            ),
            user=user,
            purpose="email verification",
        )

    async def on_after_verify(self, user: User, request: Request | None = None):
        log_security_event(
            SecurityEvent.EMAIL_VERIFIED,
            request=request,
            user_id=str(user.id),
            email=user.email,
        )

    async def _deliver(self, send: Awaitable[None], *, user: User, purpose: str) -> None:
        """Await one auth email, logging a send failure instead of raising it.

        THE RESPONSE MUST NOT DEPEND ON WHETHER THE SEND WORKED, which is why
        this swallows. `POST /auth/forgot-password` answers 202 for an address
        that has no account, an address whose account is inactive, and an
        address that was just emailed — deliberately, so the endpoint reveals
        nothing about who is registered. Letting a provider outage turn the one
        case that reaches a real mailbox into a 500 would hand back exactly that
        distinction, and would turn an outage into an account enumeration
        oracle for as long as it lasted.

        NOT SILENT, THOUGH. `logger.exception` is ERROR, which the Sentry
        logging integration captures as an event, so a provider that starts
        refusing mail surfaces as an alert rather than as a support request
        weeks later. That is the trade this makes: the person asking for the
        reset cannot be told, so the operator has to be.
        """
        try:
            await send
        except EmailSendError:
            logger.exception("Failed to send %s email to user %s", purpose, user.id)

    async def _revoke_refresh_tokens(self, user: User) -> None:
        """Revoke every refresh token family belonging to `user`.

        A PASSWORD RESET THAT LEAVES THE OLD SESSIONS ALIVE HAS NOT RECOVERED
        THE ACCOUNT. The usual reason to reset a password is that somebody else
        has it, and this application issues 15-minute access JWTs that nothing
        can revoke — but a session only outlives those by exchanging a refresh
        cookie against a row in `refresh_tokens`, so revoking the families is
        the step that actually ends the other sessions. With it the intruder
        keeps access for at most one access token lifetime; without it their
        refresh cookie goes on minting new access tokens for a week, against a
        password they no longer know.

        Written through `user_db`'s session rather than a fresh
        `async_session_maker()` one — unlike `on_after_login` above, which has
        no session to hand at the point it runs. This hook does, it is the
        session the password change was just committed through, and reusing it
        is what keeps the revocation inside the request's own connection.
        """
        session: AsyncSession = self.user_db.session
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == UUID(str(user.id)),
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await session.commit()


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager]:
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
