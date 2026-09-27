from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Valuation(Base):
    """What an item was judged to be worth, when, and by whom."""

    __tablename__ = "valuations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # A partial ISO date; see app/schemas/partial_date.py.
    valued_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    appraiser: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Free text rather than an enum: "insurance appraisal", "auction estimate",
    # "owner's estimate" and whatever else owners already call them.
    valuation_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    item = relationship("Item", back_populates="valuations")

    def __repr__(self) -> str:
        return f"<Valuation {self.value}>"
