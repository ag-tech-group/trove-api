from fastapi import APIRouter

from app.type_registry import get_all_types

router = APIRouter(tags=["collection-types"])


@router.get("/collection-types")
async def list_collection_types():
    """Return all available collection types and their field definitions."""
    return get_all_types()
