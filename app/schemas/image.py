from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    description: str | None = None
    created_at: datetime


class ImageUpdate(BaseModel):
    """Schema for updating an Image's text."""

    caption: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
