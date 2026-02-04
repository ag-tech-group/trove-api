from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models import Item
from app.models.item_note import ItemNote
from app.routers.dependencies import get_user_item
from app.schemas.item_note import ItemNoteCreate, ItemNoteRead, ItemNoteUpdate

router = APIRouter(prefix="/items/{item_id}/notes", tags=["notes"])


@router.get("", response_model=list[ItemNoteRead])
async def list_item_notes(
    item: Item = Depends(get_user_item),
):
    """List all notes for an item."""
    return item.item_notes


@router.post("", response_model=ItemNoteRead, status_code=status.HTTP_201_CREATED)
async def create_item_note(
    data: ItemNoteCreate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new note on an item."""
    note = ItemNote(
        item_id=item.id,
        **data.model_dump(),
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.patch("/{note_id}", response_model=ItemNoteRead)
async def update_item_note(
    note_id: UUID,
    data: ItemNoteUpdate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a note."""
    stmt = select(ItemNote).where(
        ItemNote.id == str(note_id),
        ItemNote.item_id == item.id,
    )
    result = await session.execute(stmt)
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await session.commit()
    await session.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_note(
    note_id: UUID,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a note."""
    stmt = select(ItemNote).where(
        ItemNote.id == str(note_id),
        ItemNote.item_id == item.id,
    )
    result = await session.execute(stmt)
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    await session.delete(note)
    await session.commit()
