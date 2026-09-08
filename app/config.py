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
