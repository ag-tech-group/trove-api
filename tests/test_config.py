import pytest
from pydantic import ValidationError

from app.config import Settings

PRODUCTION_SETTINGS = {
    "environment": "production",
    "secret_key": "s" * 32,
    "database_url": "postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
    "r2_account_id": "account-id",
    "r2_public_url": "https://images.example.com",
    "r2_bucket_name": "trove-images",
}


def test_production_accepts_complete_r2_config():
    settings = Settings(**PRODUCTION_SETTINGS)

    assert settings.r2_bucket_name == "trove-images"


@pytest.mark.parametrize("field", ["r2_account_id", "r2_public_url", "r2_bucket_name"])
def test_production_requires_r2_config(field):
    """Every R2 setting the app cannot infer must be explicit in production.

    r2_bucket_name in particular has no safe default: a production-shaped default
    would silently apply to local dev, and a dev-shaped one would silently apply
    to production.
    """
    with pytest.raises(ValidationError, match="must be set in production"):
        Settings(**{**PRODUCTION_SETTINGS, field: ""})


def test_development_does_not_require_r2_config():
    settings = Settings(
        environment="development",
        r2_account_id="",
        r2_public_url="",
        r2_bucket_name="",
    )

    assert settings.is_development
