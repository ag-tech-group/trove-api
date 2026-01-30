import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from httpx_oauth.clients.google import GoogleOAuth2

from app.auth.backend import ACCESS_TOKEN_LIFETIME, get_jwt_strategy
from app.auth.refresh import create_refresh_token, set_refresh_cookie
from app.auth.security_logging import SecurityEvent, log_security_event
from app.auth.users import get_user_manager, UserManager
from app.config import settings
from app.database import async_session_maker

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "fastapiusersoauthcsrf"
GOOGLE_SCOPES = ["openid", "email", "profile"]

google_oauth_client = GoogleOAuth2(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
)

google_oauth_router = APIRouter(prefix="/auth/google", tags=["auth"])


def _get_callback_url(request: Request) -> str:
    """Build the OAuth callback URL, respecting reverse proxy headers."""
    url = str(request.url_for("google_callback"))
    if not settings.is_development and url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def _login_redirect(error: str | None = None) -> RedirectResponse:
    """Build a redirect to the frontend login page, optionally with an error."""
    url = f"{settings.frontend_url}/login"
    if error:
        url += f"?{urlencode({'error': error})}"
    return RedirectResponse(url=url, status_code=302)


@google_oauth_router.get("/authorize")
async def google_authorize(request: Request):
    """Redirect user to Google's OAuth consent screen."""
    if not settings.google_client_id:
        return _login_redirect(error="oauth_not_configured")

    state = secrets.token_urlsafe(32)
    callback_url = _get_callback_url(request)

    authorization_url = await google_oauth_client.get_authorization_url(
        redirect_uri=callback_url,
        state=state,
        scope=GOOGLE_SCOPES,
    )

    response = RedirectResponse(url=authorization_url, status_code=302)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=state,
        max_age=300,  # 5 minutes
        path="/",
        httponly=True,
        secure=not settings.is_development,
        samesite="lax",
    )
    return response


@google_oauth_router.get("/callback")
async def google_callback(
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Handle Google's OAuth callback — exchange code, create/link user, set cookies."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error_param = request.query_params.get("error")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)

    # Google returned an error (e.g. user denied consent)
    if error_param:
        log_security_event(
            SecurityEvent.OAUTH_LOGIN_FAILURE,
            request=request,
            detail=f"google_error={error_param}",
        )
        return _login_redirect(error="oauth_denied")

    # Missing code or state
    if not code or not state:
        log_security_event(
            SecurityEvent.OAUTH_LOGIN_FAILURE,
            request=request,
            detail="missing code or state",
        )
        return _login_redirect(error="oauth_failed")

    # CSRF check
    if not csrf_cookie or csrf_cookie != state:
        log_security_event(
            SecurityEvent.OAUTH_LOGIN_FAILURE,
            request=request,
            detail="CSRF state mismatch",
        )
        return _login_redirect(error="oauth_failed")

    # Exchange authorization code for access token
    try:
        callback_url = _get_callback_url(request)
        oauth2_token = await google_oauth_client.get_access_token(
            code=code,
            redirect_uri=callback_url,
        )
    except Exception:
        logger.exception("Failed to exchange Google OAuth code")
        log_security_event(
            SecurityEvent.OAUTH_LOGIN_FAILURE,
            request=request,
            detail="token exchange failed",
        )
        return _login_redirect(error="oauth_failed")

    # Get user info and create/link account
    try:
        account_id, account_email = await google_oauth_client.get_id_email(
            oauth2_token["access_token"],
        )

        if not account_email:
            log_security_event(
                SecurityEvent.OAUTH_LOGIN_FAILURE,
                request=request,
                detail="no email from Google",
            )
            return _login_redirect(error="oauth_failed")

        user = await user_manager.oauth_callback(
            oauth_name="google",
            access_token=oauth2_token["access_token"],
            account_id=account_id,
            account_email=account_email,
            expires_at=oauth2_token.get("expires_at"),
            refresh_token=oauth2_token.get("refresh_token"),
            request=request,
            associate_by_email=True,
            is_verified_by_default=True,
        )
    except Exception:
        logger.exception("Failed to process Google OAuth callback")
        log_security_event(
            SecurityEvent.OAUTH_LOGIN_FAILURE,
            request=request,
            detail="user creation/linking failed",
        )
        return _login_redirect(error="oauth_failed")

    # Generate JWT access token
    strategy = get_jwt_strategy()
    access_token = await strategy.write_token(user)

    # Build response: redirect to frontend with auth cookies
    response = _login_redirect()

    # Set access token cookie (matches cookie_transport settings)
    response.set_cookie(
        key="trove_access",
        value=access_token,
        max_age=ACCESS_TOKEN_LIFETIME,
        path="/",
        domain=settings.cookie_domain,
        secure=not settings.is_development,
        httponly=True,
        samesite="lax",
    )

    # Create and set refresh token
    async with async_session_maker() as session:
        refresh_jwt = await create_refresh_token(str(user.id), session)
        set_refresh_cookie(response, refresh_jwt)

    # Clear CSRF cookie
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")

    log_security_event(
        SecurityEvent.OAUTH_LOGIN_SUCCESS,
        request=request,
        user_id=str(user.id),
        email=user.email,
    )

    return response
