from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models import Item
from app.models.provenance_entry import ProvenanceEntry
from app.routers.dependencies import get_user_item
from app.schemas.provenance_entry import (
    ProvenanceEntryCreate,
    ProvenanceEntryRead,
    ProvenanceEntryUpdate,
)

router = APIRouter(prefix="/items/{item_id}/provenance", tags=["provenance"])


@router.get("", response_model=list[ProvenanceEntryRead])
async def list_provenance_entries(
    item: Item = Depends(get_user_item),
):
    """List all provenance entries for an item."""
    return item.provenance_entries


@router.post("", response_model=ProvenanceEntryRead, status_code=status.HTTP_201_CREATED)
async def create_provenance_entry(
    data: ProvenanceEntryCreate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new provenance entry on an item."""
    entry = ProvenanceEntry(
        item_id=item.id,
        **data.model_dump(),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=ProvenanceEntryRead)
async def update_provenance_entry(
    entry_id: UUID,
    data: ProvenanceEntryUpdate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a provenance entry."""
    stmt = select(ProvenanceEntry).where(
        ProvenanceEntry.id == str(entry_id),
        ProvenanceEntry.item_id == item.id,
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provenance entry not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    await session.commit()
    await session.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provenance_entry(
    entry_id: UUID,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a provenance entry."""
    stmt = select(ProvenanceEntry).where(
        ProvenanceEntry.id == str(entry_id),
        ProvenanceEntry.item_id == item.id,
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provenance entry not found",
        )

    await session.delete(entry)
    await session.commit()
