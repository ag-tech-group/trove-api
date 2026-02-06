from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.tag import item_tags


class Item(Base):
    """Item in a personal collection."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Basic Info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Financials
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    acquisition_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Provenance
    artist_maker: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origin: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_era: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Physical Details
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    depth_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    materials: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Type-specific fields
    type_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="items")
    collection = relationship("Collection", back_populates="items", lazy="selectin")
    tags = relationship("Tag", secondary=item_tags, back_populates="items", lazy="selectin")
    marks = relationship(
        "Mark",
        back_populates="item",
        lazy="selectin",
        order_by="Mark.created_at",
        cascade="all, delete-orphan",
    )
    provenance_entries = relationship(
        "ProvenanceEntry",
        back_populates="item",
        lazy="selectin",
        order_by="ProvenanceEntry.created_at",
        cascade="all, delete-orphan",
    )
    item_notes = relationship(
        "ItemNote",
        back_populates="item",
        lazy="selectin",
        order_by="ItemNote.created_at",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "Image",
        back_populates="item",
        lazy="selectin",
        order_by="Image.position",
        cascade="all, delete-orphan",
    )

    @property
    def collection_name(self) -> str | None:
        return self.collection.name if self.collection else None

    def __repr__(self) -> str:
        return f"<Item {self.name}>"
