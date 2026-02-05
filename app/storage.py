import logging

import aioboto3

from app.config import settings

logger = logging.getLogger(__name__)

_session = aioboto3.Session()


def _get_endpoint_url() -> str:
    return f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"


def _get_client():
    return _session.client(
        "s3",
        endpoint_url=_get_endpoint_url(),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


async def upload_file(data: bytes, key: str, content_type: str) -> str:
    """Upload a file to R2 and return its public URL."""
    async with _get_client() as client:
        await client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    return f"{settings.r2_public_url}/{key}"


async def delete_file(key: str) -> None:
    """Delete a single file from R2. Errors are logged but not raised."""
    try:
        async with _get_client() as client:
            await client.delete_object(
                Bucket=settings.r2_bucket_name,
                Key=key,
            )
    except Exception:
        logger.exception("Failed to delete file from R2: %s", key)


async def delete_files(keys: list[str]) -> None:
    """Delete multiple files from R2. Errors are logged but not raised."""
    if not keys:
        return
    try:
        async with _get_client() as client:
            await client.delete_objects(
                Bucket=settings.r2_bucket_name,
                Delete={"Objects": [{"Key": k} for k in keys]},
            )
    except Exception:
        logger.exception("Failed to delete files from R2: %s", keys)
