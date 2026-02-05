from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.image_utils import MAX_MARK_IMAGES, validate_image_file
from app.models import Item, User
from app.models.image import Image
from app.models.mark import Mark
from app.schemas.image import ImageRead
from app.storage import delete_file, upload_file

router = APIRouter(prefix="/items/{item_id}/marks/{mark_id}/images", tags=["mark-images"])


async def _get_user_mark(
    item_id: UUID,
    mark_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Mark:
    """Fetch a mark and verify the parent item belongs to the current user."""
    stmt = select(Item).where(
        Item.id == str(item_id),
        Item.user_id == str(user.id),
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    stmt = select(Mark).where(
        Mark.id == str(mark_id),
        Mark.item_id == item.id,
    )
    result = await session.execute(stmt)
    mark = result.scalar_one_or_none()

    if not mark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mark not found",
        )

    return mark


@router.get("", response_model=list[ImageRead])
async def list_mark_images(
    mark: Mark = Depends(_get_user_mark),
):
    """List all images for a mark."""
    return mark.images


@router.post("", response_model=ImageRead, status_code=status.HTTP_201_CREATED)
async def upload_mark_image(
    file: UploadFile,
    mark: Mark = Depends(_get_user_mark),
    session: AsyncSession = Depends(get_async_session),
):
    """Upload an image for a mark."""
    # Validate file
    data = await validate_image_file(file)

    # Check image count limit
    stmt = select(Image).where(Image.mark_id == mark.id)
    result = await session.execute(stmt)
    existing = result.scalars().all()
    if len(existing) >= MAX_MARK_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_MARK_IMAGES} images per mark",
        )

    # Determine position (append to end)
    position = max((img.position for img in existing), default=-1) + 1

    # Upload to R2
    image_id = str(uuid4())
    ext = _extension_from_content_type(file.content_type)
    storage_key = f"marks/{mark.id}/{image_id}{ext}"

    # Get user_id from the parent item
    stmt = select(Item.user_id).where(Item.id == mark.item_id)
    result = await session.execute(stmt)
    user_id = result.scalar_one()

    url = await upload_file(data, storage_key, file.content_type)

    # Create DB record
    image = Image(
        id=image_id,
        user_id=user_id,
        mark_id=mark.id,
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
async def delete_mark_image(
    image_id: UUID,
    mark: Mark = Depends(_get_user_mark),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete an image from a mark."""
    stmt = select(Image).where(
        Image.id == str(image_id),
        Image.mark_id == mark.id,
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
