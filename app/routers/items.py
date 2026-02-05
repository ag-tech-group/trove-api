from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.models import Collection, Item, Tag, User
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.storage import delete_files
from app.type_registry import validate_type_fields

router = APIRouter(prefix="/items", tags=["items"])


def _escape_like(value: str) -> str:
    """Escape LIKE wildcard characters so they are matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _resolve_tags(tag_ids: list[UUID], user_id: str, session: AsyncSession) -> list:
    """Resolve tag UUIDs to Tag objects, verifying user ownership."""
    if not tag_ids:
        return []
    stmt = select(Tag).where(
        Tag.id.in_([str(tid) for tid in tag_ids]),
        Tag.user_id == user_id,
    )
    result = await session.execute(stmt)
    tags = result.scalars().all()
    if len(tags) != len(tag_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more tags not found",
        )
    return list(tags)


@router.get("", response_model=list[ItemRead])
async def list_items(
    collection_id: UUID | None = Query(default=None, description="Filter by collection"),
    tag: str | None = Query(default=None, description="Filter by tag name"),
    search: str | None = Query(
        default=None, max_length=200, description="Search in name and description"
    ),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all items for the current user with optional filters."""
    stmt = select(Item).where(Item.user_id == str(user.id))

    if collection_id is not None:
        stmt = stmt.where(Item.collection_id == str(collection_id))

    if tag is not None:
        stmt = stmt.where(Item.tags.any(Tag.name == tag))

    if search is not None:
        escaped = _escape_like(search)
        search_term = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                Item.name.ilike(search_term, escape="\\"),
                Item.description.ilike(search_term, escape="\\"),
            )
        )

    stmt = stmt.order_by(Item.created_at.desc())
    result = await session.execute(stmt)
    return result.unique().scalars().all()


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
    collection = None
    if data.collection_id is not None:
        stmt = select(Collection).where(
            Collection.id == str(data.collection_id),
            Collection.user_id == str(user.id),
        )
        result = await session.execute(stmt)
        collection = result.scalar_one_or_none()
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found",
            )

    # Resolve tags
    tags = await _resolve_tags(data.tag_ids, str(user.id), session)

    item_data = data.model_dump(exclude={"tag_ids"})
    if item_data.get("collection_id"):
        item_data["collection_id"] = str(item_data["collection_id"])
    if item_data.get("condition"):
        item_data["condition"] = item_data["condition"].value

    # Validate type_fields against the collection's type
    if item_data.get("type_fields") and collection:
        item_data["type_fields"] = validate_type_fields(collection.type, item_data["type_fields"])
    elif item_data.get("type_fields") and not collection:
        item_data["type_fields"] = None

    item = Item(
        user_id=str(user.id),
        **item_data,
    )
    item.tags = tags
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

    # Handle tags separately
    if "tag_ids" in update_data:
        tag_ids = update_data.pop("tag_ids")
        if tag_ids is not None:
            item.tags = await _resolve_tags(tag_ids, str(user.id), session)
        else:
            item.tags = []

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

    # Validate type_fields against the item's collection type
    if "type_fields" in update_data and update_data["type_fields"] is not None:
        if item.collection_id:
            stmt = select(Collection).where(Collection.id == item.collection_id)
            result = await session.execute(stmt)
            collection = result.scalar_one_or_none()
            if collection:
                update_data["type_fields"] = validate_type_fields(
                    collection.type, update_data["type_fields"]
                )
            else:
                update_data["type_fields"] = None
        else:
            update_data["type_fields"] = None

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

    # Collect storage keys before deletion for best-effort R2 cleanup
    storage_keys = [img.storage_key for img in item.images]

    await session.delete(item)
    await session.commit()

    # Best-effort R2 cleanup
    await delete_files(storage_keys)
