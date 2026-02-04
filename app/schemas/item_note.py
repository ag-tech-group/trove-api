from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ItemNoteCreate(BaseModel):
    """Schema for creating an ItemNote."""

    title: str | None = Field(default=None, max_length=200)
    body: str = Field(..., max_length=5000)


class ItemNoteUpdate(BaseModel):
    """Schema for updating an ItemNote."""

    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=5000)


class ItemNoteRead(BaseModel):
    """Schema for reading an ItemNote."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    title: str | None
    body: str
    created_at: datetime
    updated_at: datetime
