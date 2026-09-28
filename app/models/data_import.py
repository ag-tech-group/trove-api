from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    # The choices it was committed with (schemas.data_import.ImportCommit).
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # What committing created beyond items, for undo to remove if nothing else uses them.
    created_collection_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_tag_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # What committing created, which skipping entries an earlier import brought in can
    # make smaller than the preview; see schemas.data_import.ImportOutcome.
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class ImportEntry(Base):
    """One entry of the source catalog, and the item committing made of it."""

    __tablename__ = "import_entries"
    __table_args__ = (UniqueConstraint("import_id", "external_id"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    import_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The source catalog's own ID for the entry; how a second import of the same
    # catalog recognises what the first one brought in.
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Null once the owner deletes the item.
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class ImportPhoto(Base):
    """A photo the import expects the owner's browser to upload, and what became of it."""

    __tablename__ = "import_photos"
    __table_args__ = (UniqueConstraint("import_id", "filename"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    import_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Where it goes: the item, or a mark made for it. Null once that is deleted.
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    mark_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("marks.id", ondelete="SET NULL"), nullable=True
    )
    # Uploads are matched on this, the file's own name in the export.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Its place among the item's photos, in the catalog's order.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending, done, failed or skipped; see schemas.data_import.ImportPhotoStatus.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
