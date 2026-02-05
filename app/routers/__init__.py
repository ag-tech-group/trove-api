from app.routers.collection_types import router as collection_types_router
from app.routers.collections import router as collections_router
from app.routers.item_images import router as item_images_router
from app.routers.item_notes import router as item_notes_router
from app.routers.items import router as items_router
from app.routers.mark_images import router as mark_images_router
from app.routers.marks import router as marks_router
from app.routers.provenance import router as provenance_router
from app.routers.tags import router as tags_router

__all__ = [
    "collection_types_router",
    "collections_router",
    "item_images_router",
    "item_notes_router",
    "items_router",
    "mark_images_router",
    "marks_router",
    "provenance_router",
    "tags_router",
]
