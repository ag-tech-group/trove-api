from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImportSource(StrEnum):
    """Catalogs Trove can import from."""

    CATALOGIT = "catalogit"


class ImportStatus(StrEnum):
    """Where an import is: previewed, not yet committed."""

    PREVIEW = "preview"


class ImportCounts(BaseModel):
    """What committing would create."""

    items: int
    photos: int
    notes: int
    marks: int
    valuations: int
    tags: int


class ImportFieldUse(BaseModel):
    """Where one field of the source catalog goes, and in how many entries."""

    source: str
    destination: str
    count: int


class ImportIssue(BaseModel):
    """Something in the source worth a look before committing."""

    code: str
    message: str
    entry: str | None = None


class ImportGroup(BaseModel):
    """One key the items share under a way of grouping them into collections."""

    key: str
    count: int


class ImportMarkSuggestion(BaseModel):
    """A photo whose text reads like a maker's mark, signature or seal."""

    entry: str
    filename: str
    caption: str | None = None


class ImportReport(BaseModel):
    """The preview of an import."""

    entries: int
    counts: ImportCounts
    fields: list[ImportFieldUse]
    issues: list[ImportIssue]
    # Keyed by grouping: "reference_prefix" groups by the owner's reference numbers
    # ("J-Eu-12" is in "J-Eu"), "category" by the catalog's first category.
    groupings: dict[str, list[ImportGroup]]
    photos_that_look_like_marks: list[ImportMarkSuggestion]
    # Measurement systems the source used, e.g. ["imperial"].
    units: list[str]


class ImportSummary(BaseModel):
    """An import in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: ImportSource
    status: ImportStatus
    entries_filename: str
    counts: ImportCounts
    created_at: datetime


class ImportRead(ImportSummary):
    """An import with its full preview."""

    media_index_filename: str | None
    report: ImportReport
    updated_at: datetime
