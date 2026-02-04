from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MarkCreate(BaseModel):
    """Schema for creating a Mark."""

    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class MarkUpdate(BaseModel):
    """Schema for updating a Mark."""

    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class MarkRead(BaseModel):
    """Schema for reading a Mark."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    title: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
