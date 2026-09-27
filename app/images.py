"""Adding images to items and marks, and finding what storage holds for them."""

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.image_utils import MAX_ITEM_IMAGES, MAX_MARK_IMAGES, process_image, stored_filename
from app.models.image import Image
from app.models.item import Item
from app.models.mark import Mark
from app.storage import upload_file


async def add_image(
    session: AsyncSession,
    data: bytes,
    *,
    user_id: str,
    item: Item | None = None,
    mark: Mark | None = None,
    filename: str | None = None,
    caption: str | None = None,
    description: str | None = None,
    position: int | None = None,
) -> Image:
    """Process `data` and add it to `item` or `mark`, stored but not yet committed.

    Committing is left to the caller, so a caller can make adding it conditional.
    Without `position`, the image goes after the parent's others.
    """
    if item is not None:
        column, parent_id, prefix, limit, noun = (
            Image.item_id,
            item.id,
            "items",
            MAX_ITEM_IMAGES,
            "item",
        )
    else:
        column, parent_id, prefix, limit, noun = (
            Image.mark_id,
            mark.id,
            "marks",
            MAX_MARK_IMAGES,
            "mark",
        )

    positions = (
        (await session.execute(select(Image.position).where(column == parent_id))).scalars().all()
    )
    if len(positions) >= limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {limit} images per {noun}",
        )

    processed = await process_image(data)
    image_id = str(uuid4())
    storage_key = f"{prefix}/{parent_id}/{image_id}{processed.extension}"
    url = await upload_file(processed.data, storage_key, processed.content_type)

    image = Image(
        id=image_id,
        user_id=user_id,
        item_id=item.id if item is not None else None,
        mark_id=mark.id if mark is not None else None,
        filename=stored_filename(filename, processed),
        storage_key=storage_key,
        url=url,
        content_type=processed.content_type,
        size_bytes=len(processed.data),
        position=max(positions, default=-1) + 1 if position is None else position,
        width=processed.width,
        height=processed.height,
        caption=caption,
        description=description,
    )
    session.add(image)
    return image


def owned_storage_keys(item: Item) -> list[str]:
    """Everything storage holds for an item: its images, and its marks' images."""
    return [image.storage_key for image in item.images] + [
        image.storage_key for mark in item.marks for image in mark.images
    ]
