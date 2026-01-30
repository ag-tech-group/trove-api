from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from limits import RateLimitItem, parse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth import auth_backend, fastapi_users
from app.config import settings
from app.routers import categories_router, collections_router, items_router
from app.schemas.user import UserCreate, UserRead

app = FastAPI(
    title="Trove API",
    description="Personal collection management API for tracking antiques, art, and valuables",
    version="0.1.0",
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
# --- End auth routes ---

# Path-specific rate limits for auth endpoints
_AUTH_RATE_LIMITS: dict[str, RateLimitItem] = {
    "/auth/jwt/login": parse("5/minute"),
    "/auth/register": parse("3/minute"),
}


@app.middleware("http")
async def rate_limit_auth(request: Request, call_next) -> Response:
    """Apply rate limits to auth endpoints."""
    rate_limit = _AUTH_RATE_LIMITS.get(request.url.path)
    if rate_limit and request.method == "POST":
        key = get_remote_address(request)
        if not limiter._limiter.hit(rate_limit, key):
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
app.include_router(collections_router)
app.include_router(items_router)
app.include_router(categories_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Trove API"}


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {"status": "healthy"}
