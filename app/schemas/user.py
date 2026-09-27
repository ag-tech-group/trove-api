from enum import StrEnum
from uuid import UUID

from fastapi_users import schemas
from pydantic import BaseModel, Field, field_validator


class UnitSystem(StrEnum):
    """How measurements are shown. They are always stored metric."""

    METRIC = "metric"
    IMPERIAL = "imperial"


class UserRead(schemas.BaseUser[UUID]):
    """Schema for reading user data."""

    preferred_units: UnitSystem = UnitSystem.METRIC


class UserPreferencesUpdate(BaseModel):
    """Schema for `PATCH /auth/me`: the settings a user changes about themselves."""

    preferred_units: UnitSystem | None = Field(default=None)

    @field_validator("preferred_units")
    @classmethod
    def _units_cannot_be_cleared(cls, value: UnitSystem | None) -> UnitSystem:
        if value is None:
            raise ValueError("preferred_units cannot be null")
        return value


class UserCreate(schemas.BaseUserCreate):
    """Schema for creating a new user."""

    pass


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user data."""

    pass
