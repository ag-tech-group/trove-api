from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImageRead(BaseModel):
    """Schema for reading an Image."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID | None
    mark_id: UUID | None
    filename: str
    url: str
    content_type: str
    size_bytes: int
    position: int
    created_at: datetime
