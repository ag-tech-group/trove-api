from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trove_db"

    # Auth
    secret_key: str = "change-me-in-production"

    # Environment
    environment: str = "development"

    # Logging
    log_level: str = "INFO"

    # CORS — comma-separated origins, e.g. "https://trove.app,https://www.trove.app"
    cors_origins: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Frontend URL (for OAuth redirect after callback)
    frontend_url: str = "http://localhost:5173"

    # Cookie auth
    cookie_domain: str | None = None

    # Cloud Storage. ONE SETTING, NOT TWO: the public URL is derived below rather
    # than configured, because a bucket name and a separately-configured URL can
    # disagree — and when they do, uploads succeed while every image 404s. That
    # exact class of bug is what #43 and #44 were about under the previous
    # provider. Deriving it makes the two impossible to contradict.
    #
    # No credentials here at all. Cloud Run authenticates as its own service
    # account and local development uses application default credentials, so
    # there is no key pair to configure, store or rotate.
    storage_bucket_name: str = ""

    # Sentry. Empty DSN disables error monitoring entirely rather than failing,
    # so development and tests need no project. The release is baked into the
    # image at build time (see the Dockerfile) rather than set per-deploy —
    # infrastructure owns the service's shape and CI owns only the image tag, so
    # an image that carries its own release identity respects that split.
    sentry_dsn: str = ""
    sentry_release: str = ""

    # Email (Resend). The provider is not a choice this file makes: trove-infra's
    # foundation root declares the DKIM key and return-path records that let
    # Resend send as mail.trovebox.io, so the sender below is the only address
    # those records authorise and the API key is the credential that matches
    # them.
    #
    # NOT VALIDATED AS REQUIRED IN PRODUCTION, for the ordering reason the Sentry
    # comment above describes and this setting hits harder. Cloud Run resolves a
    # secret_key_ref when it creates a revision, so the key cannot be bound to
    # the service before its Secret Manager container has a payload — and if the
    # application refused to start without it, the first revision to carry this
    # code would fail. An empty key therefore disables sending rather than
    # startup; `app/email.py` is where that degrades loudly.
    resend_api_key: str = ""

    # RFC 5322 form, because Resend passes it through to the From header
    # verbatim: without the display name every client shows the raw mailbox.
    # The subdomain is deliberate — Resend signs and takes bounces under
    # mail.trovebox.io, leaving the apex's own MX and SPF to whatever ends up
    # receiving mail for trovebox.io itself.
    email_from: str = "Trove <noreply@mail.trovebox.io>"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cookie_samesite(self) -> str:
        return "lax" if self.is_development else "none"

    @property
    def storage_public_url(self) -> str:
        """Public URL base for objects in the images bucket.

        Cloud Storage serves public objects from this canonical host, so no
        custom domain and no load balancer is needed to reach them.
        """
        return f"https://storage.googleapis.com/{self.storage_bucket_name}"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.is_development:
            return [f"http://localhost:{p}" for p in range(5100, 5200)]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if not self.is_development:
            weak_secrets = {"change-me-in-production", "dev-secret-key-change-in-production", ""}
            if self.secret_key in weak_secrets or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be a strong random value in production (min 32 chars)"
                )
            if "postgres:postgres@" in self.database_url:
                raise ValueError("Default database credentials must not be used in production")
            if not self.storage_bucket_name:
                raise ValueError("STORAGE_BUCKET_NAME must be set in production")
        return self


settings = Settings()
