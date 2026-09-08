import asyncio
import logging

from google.cloud import storage
from google.cloud.exceptions import NotFound

from app.config import settings

logger = logging.getLogger(__name__)

# LAZY, AND IT HAS TO BE. storage.Client() resolves application default
# credentials at construction and raises DefaultCredentialsError when there are
# none. A module-level client would therefore make `import app.storage` fail
# anywhere without credentials — the test suite and CI included, since the tests
# patch these functions at the router but still import this module.
#
# The previous S3 client could be built at import time because botocore defers
# credential resolution to the first call. That difference is the whole reason
# this indirection exists.
_client: storage.Client | None = None


def _get_bucket() -> storage.Bucket:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client.bucket(settings.storage_bucket_name)


async def upload_file(data: bytes, key: str, content_type: str) -> str:
    """Upload a file to Cloud Storage and return its public URL."""

    def _upload() -> None:
        _get_bucket().blob(key).upload_from_string(data, content_type=content_type)

    # The GCS client is synchronous, unlike the aioboto3 client it replaces, so
    # every call goes to a worker thread. Calling it directly would block the
    # event loop for the whole upload and stall every other request in flight.
    await asyncio.to_thread(_upload)
    return f"{settings.storage_public_url}/{key}"


async def delete_file(key: str) -> None:
    """Delete a single file from Cloud Storage. Errors are logged but not raised."""

    def _delete() -> None:
        _get_bucket().blob(key).delete()

    try:
        await asyncio.to_thread(_delete)
    except NotFound:
        # S3 deletes are idempotent and GCS deletes are not: removing an object
        # that is already gone raises here where it used to succeed silently.
        # That is the expected outcome of a retry, not a fault, so it must not
        # reach the exception log and read as a real failure.
        logger.info("File already absent from storage: %s", key)
    except Exception:
        logger.exception("Failed to delete file from storage: %s", key)


async def delete_files(keys: list[str]) -> None:
    """Delete multiple files from Cloud Storage. Errors are logged but not raised."""
    if not keys:
        return

    def _delete_many() -> None:
        bucket = _get_bucket()
        for key in keys:
            try:
                bucket.blob(key).delete()
            except NotFound:
                logger.info("File already absent from storage: %s", key)

    # A loop rather than the client's batch context, deliberately. This is called
    # with the images belonging to one item or mark — single digits — so batching
    # would save one round trip at the cost of a failure mode where one bad key
    # obscures the rest. Per-key handling means a missing object cannot prevent
    # the others being deleted.
    try:
        await asyncio.to_thread(_delete_many)
    except Exception:
        logger.exception("Failed to delete files from storage: %s", keys)
