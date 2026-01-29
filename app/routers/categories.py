from fastapi import APIRouter, Depends
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.database import get_async_session
from app.models import Item, User

router = APIRouter(prefix="/categories", tags=["categories"])

SUGGESTED_CATEGORIES = [
    "Antique",
    "Art",
    "Book",
    "Ceramic",
    "Clock/Watch",
    "Coin/Currency",
    "Collectible",
    "Doll/Toy",
    "Furniture",
    "Glass",
    "Jewelry",
    "Memorabilia",
    "Musical Instrument",
    "Photograph",
    "Sculpture",
    "Silver",
    "Stamp",
    "Textile",
    "Tool",
    "Other",
]


@router.get("", response_model=list[str])
async def list_categories(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List suggested categories plus user's custom categories."""
    # Get user's custom categories (categories not in suggested list)
    stmt = select(distinct(Item.category)).where(
        Item.user_id == str(user.id),
        Item.category.isnot(None),
        Item.category != "",
    )
    result = await session.execute(stmt)
    user_categories = {row[0] for row in result.all()}

    # Combine suggested categories with user's custom ones
    all_categories = set(SUGGESTED_CATEGORIES) | user_categories

    return sorted(all_categories)
