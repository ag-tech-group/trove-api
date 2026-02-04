from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.models import Tag, User
from app.schemas.tag import TagCreate, TagRead, TagUpdate

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
async def list_tags(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all tags for the current user, sorted alphabetically."""
    stmt = select(Tag).where(Tag.user_id == str(user.id)).order_by(Tag.name)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    data: TagCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new tag. Returns 409 if a tag with the same name already exists."""
    stmt = select(Tag).where(Tag.user_id == str(user.id), Tag.name == data.name)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag with this name already exists",
        )

    tag = Tag(user_id=str(user.id), name=data.name)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: UUID,
    data: TagUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Rename a tag."""
    stmt = select(Tag).where(Tag.id == str(tag_id), Tag.user_id == str(user.id))
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )

    # Check for duplicate name
    stmt = select(Tag).where(
        Tag.user_id == str(user.id),
        Tag.name == data.name,
        Tag.id != str(tag_id),
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag with this name already exists",
        )

    tag.name = data.name
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a tag. Removes it from all items automatically."""
    stmt = select(Tag).where(Tag.id == str(tag_id), Tag.user_id == str(user.id))
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )

    await session.delete(tag)
    await session.commit()
