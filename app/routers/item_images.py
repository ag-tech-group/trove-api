from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.image_utils import MAX_ITEM_IMAGES, validate_image_file
from app.models import Item
from app.models.image import Image
from app.routers.dependencies import get_user_item
from app.schemas.image import ImageRead
from app.storage import delete_file, upload_file

router = APIRouter(prefix="/items/{item_id}/images", tags=["item-images"])


@router.get("", response_model=list[ImageRead])
async def list_item_images(
    item: Item = Depends(get_user_item),
):
    """List all images for an item."""
    return item.images


@router.post("", response_model=ImageRead, status_code=status.HTTP_201_CREATED)
async def upload_item_image(
    file: UploadFile,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Upload an image for an item."""
    # Validate file
    data = await validate_image_file(file)

    # Check image count limit
    stmt = select(Image).where(Image.item_id == item.id)
    result = await session.execute(stmt)
    existing = result.scalars().all()
    if len(existing) >= MAX_ITEM_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_ITEM_IMAGES} images per item",
        )

    # Determine position (append to end)
    position = max((img.position for img in existing), default=-1) + 1

    # Upload to R2
    image_id = str(uuid4())
    ext = _extension_from_content_type(file.content_type)
    storage_key = f"items/{item.id}/{image_id}{ext}"
    url = await upload_file(data, storage_key, file.content_type)

    # Create DB record
    image = Image(
        id=image_id,
        user_id=item.user_id,
        item_id=item.id,
        filename=file.filename or f"image{ext}",
        storage_key=storage_key,
        url=url,
        content_type=file.content_type,
        size_bytes=len(data),
        position=position,
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_image(
    image_id: UUID,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete an image from an item."""
    stmt = select(Image).where(
        Image.id == str(image_id),
        Image.item_id == item.id,
    )
    result = await session.execute(stmt)
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    storage_key = image.storage_key
    await session.delete(image)
    await session.commit()

    # Best-effort R2 cleanup
    await delete_file(storage_key)


def _extension_from_content_type(content_type: str | None) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(content_type or "", ".bin")
