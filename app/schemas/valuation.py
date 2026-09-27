from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.partial_date import PartialDate


class ValuationCreate(BaseModel):
    """Schema for creating a Valuation."""

    value: Decimal = Field(..., ge=0, decimal_places=2)
    valued_on: PartialDate | None = Field(default=None)
    appraiser: str | None = Field(default=None, max_length=200)
    valuation_type: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)


class ValuationUpdate(BaseModel):
    """Schema for updating a Valuation."""

    value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    valued_on: PartialDate | None = Field(default=None)
    appraiser: str | None = Field(default=None, max_length=200)
    valuation_type: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("value")
    @classmethod
    def _value_cannot_be_cleared(cls, value: Decimal | None) -> Decimal:
        # Omit it to leave it unchanged; a valuation without a value isn't one.
        if value is None:
            raise ValueError("value cannot be null")
        return value


class ValuationRead(BaseModel):
    """Schema for reading a Valuation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    value: Decimal
    valued_on: str | None
    appraiser: str | None
    valuation_type: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
