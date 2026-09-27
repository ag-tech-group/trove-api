from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

DEFAULT_UNITS = "metric"


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model for authentication.

    Inherits from FastAPI-Users base which provides:
    - id: UUID primary key
    - email: unique email address
    - hashed_password: bcrypt hashed password
    - is_active: whether user can authenticate
    - is_superuser: admin privileges
    - is_verified: email verification status
    """

    # Measurements are stored metric; this only chooses how they are shown.
    preferred_units: Mapped[str] = mapped_column(
        String(10), nullable=False, default=DEFAULT_UNITS, server_default=DEFAULT_UNITS
    )

    def __init__(self, **kwargs):
        # Column defaults only apply on INSERT; an unsaved User should carry it too.
        kwargs.setdefault("preferred_units", DEFAULT_UNITS)
        super().__init__(**kwargs)

    oauth_accounts = relationship("OAuthAccount", lazy="joined")
    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")
