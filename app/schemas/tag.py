from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    """Schema for creating a Tag."""

    name: str = Field(..., max_length=100)


class TagUpdate(BaseModel):
    """Schema for updating a Tag."""

    name: str = Field(..., max_length=100)


class TagRead(BaseModel):
    """Schema for reading a Tag."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
