from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Condition(str, Enum):
    """Condition of an item."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class ItemBase(BaseModel):
    """Base schema for Item."""

    # Basic Info
    name: str = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=100)
    condition: Condition | None = Field(default=None)
    location: str | None = Field(default=None, max_length=200)

    # Financials
    acquisition_date: date | None = Field(default=None)
    acquisition_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    estimated_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    # Provenance
    artist_maker: str | None = Field(default=None, max_length=200)
    origin: str | None = Field(default=None, max_length=200)
    date_era: str | None = Field(default=None, max_length=100)
    provenance_notes: str | None = Field(default=None, max_length=5000)

    # Physical Details
    height_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    width_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    depth_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    weight_kg: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    materials: str | None = Field(default=None, max_length=500)

    # Metadata
    notes: str | None = Field(default=None, max_length=5000)


class ItemCreate(ItemBase):
    """Schema for creating an Item."""

    collection_id: UUID | None = Field(default=None)


class ItemUpdate(BaseModel):
    """Schema for updating an Item."""

    # Basic Info
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=100)
    condition: Condition | None = Field(default=None)
    location: str | None = Field(default=None, max_length=200)

    # Collection
    collection_id: UUID | None = Field(default=None)

    # Financials
    acquisition_date: date | None = Field(default=None)
    acquisition_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    estimated_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    # Provenance
    artist_maker: str | None = Field(default=None, max_length=200)
    origin: str | None = Field(default=None, max_length=200)
    date_era: str | None = Field(default=None, max_length=100)
    provenance_notes: str | None = Field(default=None, max_length=5000)

    # Physical Details
    height_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    width_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    depth_cm: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    weight_kg: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    materials: str | None = Field(default=None, max_length=500)

    # Metadata
    notes: str | None = Field(default=None, max_length=5000)


class ItemRead(ItemBase):
    """Schema for reading an Item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    collection_id: UUID | None
    created_at: datetime
    updated_at: datetime
