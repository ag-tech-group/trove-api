from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Image(Base):
    """Image attached to an item or a mark."""

    __tablename__ = "images"

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
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    mark_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("marks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User")
    item = relationship("Item", back_populates="images")
    mark = relationship("Mark", back_populates="images")

    __table_args__ = (
        CheckConstraint(
            "(item_id IS NOT NULL AND mark_id IS NULL) OR "
            "(item_id IS NULL AND mark_id IS NOT NULL)",
            name="ck_images_exactly_one_parent",
        ),
    )

    def __repr__(self) -> str:
        return f"<Image {self.filename}>"
