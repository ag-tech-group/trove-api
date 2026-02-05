from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models import Item
from app.models.mark import Mark
from app.routers.dependencies import get_user_item
from app.schemas.mark import MarkCreate, MarkRead, MarkUpdate
from app.storage import delete_files

router = APIRouter(prefix="/items/{item_id}/marks", tags=["marks"])


@router.get("", response_model=list[MarkRead])
async def list_marks(
    item: Item = Depends(get_user_item),
):
    """List all marks for an item."""
    return item.marks


@router.post("", response_model=MarkRead, status_code=status.HTTP_201_CREATED)
async def create_mark(
    data: MarkCreate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new mark on an item."""
    mark = Mark(
        item_id=item.id,
        **data.model_dump(),
    )
    session.add(mark)
    await session.commit()
    await session.refresh(mark)
    return mark


@router.patch("/{mark_id}", response_model=MarkRead)
async def update_mark(
    mark_id: UUID,
    data: MarkUpdate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a mark."""
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

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mark, field, value)

    await session.commit()
    await session.refresh(mark)
    return mark


@router.delete("/{mark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mark(
    mark_id: UUID,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a mark."""
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

    # Collect storage keys before deletion for best-effort R2 cleanup
    storage_keys = [img.storage_key for img in mark.images]

    await session.delete(mark)
    await session.commit()

    # Best-effort R2 cleanup
    await delete_files(storage_keys)
