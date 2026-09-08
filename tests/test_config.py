import pytest
from pydantic import ValidationError

from app.config import Settings

PRODUCTION_SETTINGS = {
    "environment": "production",
    "secret_key": "s" * 32,
    "database_url": "postgresql+asyncpg://trove:strong-password@db:5432/trove_db",
    "storage_bucket_name": "trove-images",
}


def test_production_accepts_complete_storage_config():
    settings = Settings(**PRODUCTION_SETTINGS)

    assert settings.storage_bucket_name == "trove-images"


def test_production_requires_storage_bucket_name():
    """The bucket name has no safe default, so production must state it.

    A production-shaped default would silently apply to local dev and a
    dev-shaped one would silently apply to production — which is why this is
    checked rather than defaulted.
    """
    with pytest.raises(ValidationError, match="must be set in production"):
        Settings(**{**PRODUCTION_SETTINGS, "storage_bucket_name": ""})


def test_development_does_not_require_storage_config():
    settings = Settings(environment="development", storage_bucket_name="")

    assert settings.is_development


def test_public_url_is_derived_from_the_bucket_name():
    """The public URL is not configurable, and that is the point.

    When the URL was a separate setting it could name a different bucket than
    the one being written to, and the failure was invisible: uploads succeeded
    and every image 404ed. Deriving it makes the two impossible to contradict.
    """
    settings = Settings(**PRODUCTION_SETTINGS)

    assert settings.storage_public_url == "https://storage.googleapis.com/trove-images"


def test_public_url_follows_the_bucket_it_is_given():
    dev = Settings(environment="development", storage_bucket_name="trove-images-dev")

    assert dev.storage_public_url == "https://storage.googleapis.com/trove-images-dev"
