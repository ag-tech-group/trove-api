from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from limits import RateLimitItem, parse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import auth_backend, current_active_user, fastapi_users
from app.auth.oauth import google_oauth_router
from app.auth.security_logging import SecurityEvent, log_security_event
from app.config import settings
from app.logging import setup_logging
from app.models.user import User
from app.routers import (
    collection_types_router,
    collections_router,
    item_images_router,
    item_notes_router,
    items_router,
    mark_images_router,
    marks_router,
    provenance_router,
    tags_router,
)
from app.routers.auth_refresh import router as auth_refresh_router
from app.schemas.user import UserCreate, UserRead
from app.sentry import init_sentry

# --- Observability ---
# BOTH CALLS MUST STAY ABOVE `app = FastAPI(...)`. The Sentry SDK's Starlette and
# FastAPI integrations auto-instrument the middleware stack at app construction
# time, so initialising after it silently loses request context — URL, method,
# headers — on every captured event. Nothing fails and events still arrive; they
# just stop being actionable. `setup_logging()` leads so that anything the rest
# of module import emits is already formatted.
setup_logging()
init_sentry()

app = FastAPI(
    title="Trove API",
    description="Personal collection management API for tracking antiques, art, and valuables",
    version="0.2.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Auth routes ---
# Custom refresh/logout routes (included before FastAPI-Users so /auth/jwt/logout is shadowed)
app.include_router(auth_refresh_router)
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
# POST /auth/forgot-password and POST /auth/reset-password. Both existed as
# handlers in `app/auth/users.py` long before this line did — `fastapi-users`
# builds the routes but mounting them is the application's choice, so until the
# email service existed to carry the token the hooks were unreachable code.
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
# POST /auth/request-verify-token and POST /auth/verify.
#
# MOUNTING THESE DOES NOT MAKE VERIFICATION MANDATORY. `current_active_user` is
# `current_user(active=True)`, so nothing in the API checks `is_verified` and
# registration still grants immediate access. These endpoints let an account
# confirm its address; requiring it before login is a product decision, and
# would be a one-word change here that locks out every account registered
# before it.
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(google_oauth_router)
# --- End auth routes ---


@app.get("/auth/me", response_model=UserRead, tags=["auth"])
async def get_current_user(user: User = Depends(current_active_user)):
    return user


# Path-specific rate limits for auth endpoints
_AUTH_RATE_LIMITS: dict[str, RateLimitItem] = {
    "/auth/jwt/login": parse("5/minute"),
    "/auth/register": parse("3/minute"),
    "/auth/refresh": parse("30/minute"),
    "/auth/google/authorize": parse("10/minute"),
    "/auth/google/callback": parse("10/minute"),
    # THE TWO THAT SEND MAIL ARE THE TIGHTEST HERE, and not because of the
    # database cost. An unauthenticated caller names the recipient, so an
    # unlimited endpoint is a way to flood a stranger's inbox from Trove's
    # sending domain — which spends the domain's reputation, the one asset the
    # DKIM records in trove-infra exist to build. The quiet 202 these return for
    # an unregistered address also makes them the natural place to probe for who
    # has an account, and a low ceiling is what makes that expensive.
    "/auth/forgot-password": parse("3/minute"),
    "/auth/request-verify-token": parse("3/minute"),
    # The token-consuming halves are guessing surfaces rather than sending ones.
    # Both tokens are HMAC-signed JWTs, so forgery is not the threat a limit
    # addresses; this just denies a client the volume to try.
    "/auth/reset-password": parse("5/minute"),
    "/auth/verify": parse("5/minute"),
}

# OAuth endpoints use GET instead of POST
_OAUTH_PATHS = {"/auth/google/authorize", "/auth/google/callback"}

# Global default for every other route, matching the per-client-IP keying of
# the auth limits. Enforced here in-house (limits via limiter._limiter)
# rather than through slowapi's SlowAPIMiddleware, whose default_limits
# enforcement FastAPI >=0.137 breaks for routes mounted via include_router
# (slowapi issue #281).
_DEFAULT_RATE_LIMIT: RateLimitItem = parse("300/minute")

# Infrastructure paths that must never 429: probes, docs, and the security
# contact file.
_RATE_LIMIT_EXEMPT_PATHS = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/.well-known/security.txt",
}


@app.middleware("http")
async def rate_limit(request: Request, call_next) -> Response:
    """Apply rate limits.

    Auth endpoints get their strict per-path limits; every other route gets
    the global default except the exempt infrastructure paths. A request
    that consumed an auth limit does not also consume the default bucket.
    """
    path = request.url.path
    auth_limit = _AUTH_RATE_LIMITS.get(path)
    is_oauth = path in _OAUTH_PATHS
    if auth_limit and (request.method == "POST" or is_oauth):
        rate_limit_item: RateLimitItem | None = auth_limit
    elif path in _RATE_LIMIT_EXEMPT_PATHS:
        rate_limit_item = None
    else:
        rate_limit_item = _DEFAULT_RATE_LIMIT
    if rate_limit_item is not None:
        key = get_remote_address(request)
        if not limiter._limiter.hit(rate_limit_item, key):
            log_security_event(
                SecurityEvent.RATE_LIMIT_HIT,
                request=request,
                detail=f"path={path}",
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# API routes
app.include_router(collection_types_router)
app.include_router(collections_router)
app.include_router(items_router)
app.include_router(tags_router)
app.include_router(marks_router)
app.include_router(item_images_router)
app.include_router(mark_images_router)
app.include_router(provenance_router)
app.include_router(item_notes_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Trove API"}


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {"status": "healthy"}
