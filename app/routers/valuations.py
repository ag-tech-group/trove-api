from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models import Item
from app.models.valuation import Valuation
from app.routers.dependencies import get_user_item
from app.schemas.valuation import ValuationCreate, ValuationRead, ValuationUpdate

router = APIRouter(prefix="/items/{item_id}/valuations", tags=["valuations"])


@router.get("", response_model=list[ValuationRead])
async def list_valuations(
    item: Item = Depends(get_user_item),
):
    """List all valuations of an item."""
    return item.valuations


@router.post("", response_model=ValuationRead, status_code=status.HTTP_201_CREATED)
async def create_valuation(
    data: ValuationCreate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Record a valuation of an item."""
    valuation = Valuation(
        item_id=item.id,
        **data.model_dump(),
    )
    session.add(valuation)
    await session.commit()
    await session.refresh(valuation)
    return valuation


@router.patch("/{valuation_id}", response_model=ValuationRead)
async def update_valuation(
    valuation_id: UUID,
    data: ValuationUpdate,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a valuation."""
    valuation = await _get_valuation(valuation_id, item, session)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(valuation, field, value)

    await session.commit()
    await session.refresh(valuation)
    return valuation


@router.delete("/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_valuation(
    valuation_id: UUID,
    item: Item = Depends(get_user_item),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a valuation."""
    valuation = await _get_valuation(valuation_id, item, session)
    await session.delete(valuation)
    await session.commit()


async def _get_valuation(valuation_id: UUID, item: Item, session: AsyncSession) -> Valuation:
    stmt = select(Valuation).where(
        Valuation.id == str(valuation_id),
        Valuation.item_id == item.id,
    )
    result = await session.execute(stmt)
    valuation = result.scalar_one_or_none()

    if not valuation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valuation not found",
        )

    return valuation
