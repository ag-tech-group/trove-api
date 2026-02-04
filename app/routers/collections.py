from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.models import Collection, Item, User
from app.schemas.collection import (
    CollectionCreate,
    CollectionRead,
    CollectionReadWithCount,
    CollectionUpdate,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionReadWithCount])
async def list_collections(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all collections for the current user."""
    # Get collections with item counts
    stmt = (
        select(Collection, func.count(Item.id).label("item_count"))
        .outerjoin(Item, Collection.id == Item.collection_id)
        .where(Collection.user_id == str(user.id))
        .group_by(Collection.id)
        .order_by(Collection.name)
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        CollectionReadWithCount(
            id=row.Collection.id,
            user_id=row.Collection.user_id,
            name=row.Collection.name,
            description=row.Collection.description,
            type=row.Collection.type,
            created_at=row.Collection.created_at,
            updated_at=row.Collection.updated_at,
            item_count=row.item_count,
        )
        for row in rows
    ]


@router.get("/{collection_id}", response_model=CollectionReadWithCount)
async def get_collection(
    collection_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get a single collection by ID."""
    stmt = (
        select(Collection, func.count(Item.id).label("item_count"))
        .outerjoin(Item, Collection.id == Item.collection_id)
        .where(Collection.id == str(collection_id), Collection.user_id == str(user.id))
        .group_by(Collection.id)
    )
    result = await session.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    return CollectionReadWithCount(
        id=row.Collection.id,
        user_id=row.Collection.user_id,
        name=row.Collection.name,
        description=row.Collection.description,
        type=row.Collection.type,
        created_at=row.Collection.created_at,
        updated_at=row.Collection.updated_at,
        item_count=row.item_count,
    )


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new collection."""
    collection = Collection(
        user_id=str(user.id),
        name=data.name,
        description=data.description,
        type=data.type,
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection)
    return collection


@router.patch("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a collection."""
    stmt = select(Collection).where(
        Collection.id == str(collection_id),
        Collection.user_id == str(user.id),
    )
    result = await session.execute(stmt)
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    await session.commit()
    await session.refresh(collection)
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a collection. Items in the collection become uncategorized."""
    stmt = select(Collection).where(
        Collection.id == str(collection_id),
        Collection.user_id == str(user.id),
    )
    result = await session.execute(stmt)
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    await session.delete(collection)
    await session.commit()
