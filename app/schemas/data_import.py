from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.image import ImageRead


class ImportSource(StrEnum):
    """Catalogs Trove can import from."""

    CATALOGIT = "catalogit"


class ImportStatus(StrEnum):
    """Previewed; committed and waiting for photos; or done."""

    PREVIEW = "preview"
    IMPORTING = "importing"
    COMPLETED = "completed"


class ImportPhotoStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    # Entries an earlier import of this catalog already brought into the account, as
    # of the preview. Committing leaves them out unless told otherwise.
    already_imported: int = 0


class ImportSummary(BaseModel):
    """An import in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: ImportSource
    status: ImportStatus
    entries_filename: str
    counts: ImportCounts
    created_at: datetime


class ImportPhotoProgress(BaseModel):
    """How far the photo uploads have got."""

    total: int = 0
    pending: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0


class ImportOutcome(BaseModel):
    """What committing created."""

    items: int
    # Left out because an earlier import already brought them in.
    skipped: int
    photos: int


class ImportPhotoFailure(BaseModel):
    filename: str
    error: str | None


class ImportRead(ImportSummary):
    """An import with its full preview, and its progress once committed."""

    media_index_filename: str | None
    report: ImportReport
    updated_at: datetime
    committed_at: datetime | None = None
    completed_at: datetime | None = None
    outcome: ImportOutcome | None = None
    photos: ImportPhotoProgress = Field(default_factory=ImportPhotoProgress)
    # The file names still expected, for the browser to find in the export's zips.
    pending_photos: list[str] = Field(default_factory=list)
    failed_photos: list[ImportPhotoFailure] = Field(default_factory=list)


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CollectionTarget(BaseModel):
    """A collection by `id`, or by `name`: the account's collection of that name, compared
    ignoring case, or a new one if it has none. Keys naming the same collection share it.
    """

    id: UUID | None = None
    name: Name | None = None

    @model_validator(mode="after")
    def _one_of(self) -> CollectionTarget:
        if (self.id is None) == (self.name is None):
            raise ValueError("give a collection's id or a new collection's name, not both")
        return self


class ImportTarget(BaseModel):
    """Where a group of items goes: a collection, if any, and tags added to each."""

    collection: CollectionTarget | None = None
    tags: list[TagName] = Field(default_factory=list, max_length=20)


class ImportCommit(BaseModel):
    """Commit a previewed import: create its items and wait for its photos."""

    # How items are grouped for `groups`: by the keys the preview reported under
    # report.groupings. Without it, every item goes to `default`.
    grouping: Literal["reference_prefix", "category"] | None = None
    # Keyed by grouping key, compared ignoring case.
    groups: dict[str, ImportTarget] = Field(default_factory=dict)
    # For items with no key, or a key not in `groups`.
    default: ImportTarget = Field(default_factory=ImportTarget)
    # Photos, by file name, to put on a new mark of their item rather than on the
    # item itself; e.g. from report.photos_that_look_like_marks.
    mark_photos: list[str] = Field(default_factory=list)
    # Leave out entries an earlier import of the same catalog already created.
    skip_already_imported: bool = True

    @model_validator(mode="after")
    def _groups_need_a_grouping(self) -> ImportCommit:
        if self.groups and self.grouping is None:
            raise ValueError("groups needs a grouping")
        return self


class ImportPhotoRead(BaseModel):
    """One expected photo, after an upload."""

    filename: str
    status: ImportPhotoStatus
    error: str | None = None
    image: ImageRead | None = None
