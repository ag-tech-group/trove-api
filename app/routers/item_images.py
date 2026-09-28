from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.image_utils import validate_image_file
from app.images import add_image
from app.models import Item
from app.models.image import Image
from app.routers.dependencies import get_user_item
from app.schemas.image import ImageRead, ImageUpdate
from app.storage import delete_file

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
    data = await validate_image_file(file)
    image = await add_image(session, data, user_id=item.user_id, item=item, filename=file.filename)
    await session.commit()
    await session.refresh(image)
    return image


@router.patch("/{image_id}", response_model=ImageRead)
async def update_item_image(
    image_id: UUID,
    data: ImageUpdate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Update an image's caption or description."""
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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(image, field, value)

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

    # Best-effort object storage cleanup
    await delete_file(storage_key)
