from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceEntryCreate(BaseModel):
    """Schema for creating a ProvenanceEntry."""

    owner_name: str = Field(..., max_length=200)
    date_from: str | None = Field(default=None, max_length=100)
    date_to: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)


class ProvenanceEntryUpdate(BaseModel):
    """Schema for updating a ProvenanceEntry."""

    owner_name: str | None = Field(default=None, max_length=200)
    date_from: str | None = Field(default=None, max_length=100)
    date_to: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)


class ProvenanceEntryRead(BaseModel):
    """Schema for reading a ProvenanceEntry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    owner_name: str
    date_from: str | None
    date_to: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
