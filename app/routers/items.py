from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.models import Collection, Item, User
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemRead])
async def list_items(
    collection_id: UUID | None = Query(default=None, description="Filter by collection"),
    category: str | None = Query(default=None, description="Filter by category"),
    search: str | None = Query(default=None, description="Search in name and description"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all items for the current user with optional filters."""
    stmt = select(Item).where(Item.user_id == str(user.id))

    if collection_id is not None:
        stmt = stmt.where(Item.collection_id == str(collection_id))

    if category is not None:
        stmt = stmt.where(Item.category == category)

    if search is not None:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Item.name.ilike(search_term),
                Item.description.ilike(search_term),
            )
        )

    stmt = stmt.order_by(Item.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get a single item by ID."""
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

    return item


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new item."""
    # Verify collection belongs to user if provided
    if data.collection_id is not None:
        stmt = select(Collection).where(
            Collection.id == str(data.collection_id),
            Collection.user_id == str(user.id),
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found",
            )

    item_data = data.model_dump()
    if item_data.get("collection_id"):
        item_data["collection_id"] = str(item_data["collection_id"])
    if item_data.get("condition"):
        item_data["condition"] = item_data["condition"].value

    item = Item(
        user_id=str(user.id),
        **item_data,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: UUID,
    data: ItemUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Update an item."""
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

    update_data = data.model_dump(exclude_unset=True)

    # Verify collection belongs to user if being updated
    if "collection_id" in update_data and update_data["collection_id"] is not None:
        stmt = select(Collection).where(
            Collection.id == str(update_data["collection_id"]),
            Collection.user_id == str(user.id),
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found",
            )
        update_data["collection_id"] = str(update_data["collection_id"])

    # Convert condition enum to string value
    if "condition" in update_data and update_data["condition"] is not None:
        update_data["condition"] = update_data["condition"].value

    for field, value in update_data.items():
        setattr(item, field, value)

    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete an item."""
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

    await session.delete(item)
    await session.commit()
