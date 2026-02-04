from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.type_registry import COLLECTION_TYPES


class CollectionBase(BaseModel):
    """Base schema for Collection."""

    name: str = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    type: str = Field(default="general", max_length=50)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in COLLECTION_TYPES:
            raise ValueError(f"Unknown collection type: {v}")
        return v


class CollectionCreate(CollectionBase):
    """Schema for creating a Collection."""

    pass


class CollectionUpdate(BaseModel):
    """Schema for updating a Collection."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    type: str | None = Field(default=None, max_length=50)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v not in COLLECTION_TYPES:
            raise ValueError(f"Unknown collection type: {v}")
        return v


class CollectionRead(CollectionBase):
    """Schema for reading a Collection."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class CollectionReadWithCount(CollectionRead):
    """Schema for reading a Collection with item count."""

    item_count: int = 0
