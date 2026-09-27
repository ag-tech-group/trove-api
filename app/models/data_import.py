from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Import(Base):
    """A catalog brought over from another app: its preview, then what it created."""

    __tablename__ = "imports"

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
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    entries_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_index_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The uploaded export, parsed but not mapped. Committing plans from this again
    # rather than trusting a stored plan. Deferred: it can run to megabytes, and
    # nothing but committing needs it.
    source_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, deferred=True)
    # The preview; see ImportPlan.report().
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
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

    @property
    def counts(self) -> dict[str, int]:
        return self.report["counts"]

    def __repr__(self) -> str:
        return f"<Import {self.source} {self.status}>"
