from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.image_utils import validate_image_file
from app.images import add_image
from app.models import Item, User
from app.models.image import Image
from app.models.mark import Mark
from app.schemas.image import ImageRead, ImageUpdate
from app.storage import delete_file

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
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Upload an image for a mark."""
    data = await validate_image_file(file)
    image = await add_image(session, data, user_id=str(user.id), mark=mark, filename=file.filename)
    await session.commit()
    await session.refresh(image)
    return image


@router.patch("/{image_id}", response_model=ImageRead)
async def update_mark_image(
    image_id: UUID,
    data: ImageUpdate,
    mark: Mark = Depends(_get_user_mark),
    session: AsyncSession = Depends(get_async_session),
):
    """Update an image's caption or description."""
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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(image, field, value)

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

    # Best-effort object storage cleanup
    await delete_file(storage_key)
