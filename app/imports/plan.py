"""What an import would create, independent of the catalog it came from.

A source parser (app/imports/catalogit.py is the first) turns an export into an
ImportPlan. The preview reports on the plan; committing it creates what it lists.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class PlannedPhoto:
    # The path the export lists, and the file name uploads are matched on.
    path: str
    filename: str
    caption: str | None = None
    description: str | None = None
    # Its text reads like a maker's mark, signature or seal, so it may belong on a
    # mark rather than on the item. A suggestion for the person importing, only.
    looks_like_mark: bool = False


@dataclass
class PlannedNote:
    title: str
    body: str


@dataclass
class PlannedMark:
    title: str | None
    description: str | None


@dataclass
class PlannedValuation:
    value: Decimal
    valued_on: str | None = None
    appraiser: str | None = None
    valuation_type: str | None = None
    notes: str | None = None


@dataclass
class PlannedItem:
    external_id: str
    # Item columns, already within their limits.
    fields: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    notes: list[PlannedNote] = field(default_factory=list)
    marks: list[PlannedMark] = field(default_factory=list)
    valuations: list[PlannedValuation] = field(default_factory=list)
    photos: list[PlannedPhoto] = field(default_factory=list)
    # The key this item has under each way of grouping the import into collections.
    groups: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.fields.get("reference_number") or self.fields["name"]


@dataclass
class ImportIssue:
    code: str
    message: str
    entry: str | None = None


class FieldUse:
    """Where each field of the source went, counted across entries."""

    def __init__(self) -> None:
        self._uses: dict[str, Counter[str]] = defaultdict(Counter)

    def record(self, source: str, destination: str) -> None:
        self._uses[source][destination] += 1

    def rows(self) -> list[dict[str, Any]]:
        return [
            {"source": source, "destination": destination, "count": count}
            for source, destinations in sorted(self._uses.items())
            for destination, count in destinations.most_common()
        ]


@dataclass
class ImportPlan:
    items: list[PlannedItem]
    issues: list[ImportIssue]
    fields: FieldUse
    # Measurement systems the source wrote its dimensions in.
    units: set[str]
    entries: int

    def report(self) -> dict[str, Any]:
        """The preview: what committing would create, and what needs a look first."""
        # Keys differing only in case are one group ("P-J" and "P-j"), shown in the
        # spelling most entries use.
        spellings: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
        for item in self.items:
            for mode, key in item.groups.items():
                spellings[mode][key.casefold()][key] += 1
        groupings = {
            mode: Counter(
                {variants.most_common(1)[0][0]: variants.total() for variants in keys.values()}
            )
            for mode, keys in spellings.items()
        }
        photos = [photo for item in self.items for photo in item.photos]
        return {
            "entries": self.entries,
            "counts": {
                "items": len(self.items),
                "photos": len(photos),
                "notes": sum(len(item.notes) for item in self.items),
                "marks": sum(len(item.marks) for item in self.items),
                "valuations": sum(len(item.valuations) for item in self.items),
                "tags": len({tag.casefold() for item in self.items for tag in item.tags}),
            },
            "fields": self.fields.rows(),
            "issues": [vars(issue) for issue in self.issues],
            "groupings": {
                mode: [{"key": key, "count": count} for key, count in counter.most_common()]
                for mode, counter in sorted(groupings.items())
            },
            "photos_that_look_like_marks": [
                {"entry": item.label, "filename": photo.filename, "caption": photo.caption}
                for item in self.items
                for photo in item.photos
                if photo.looks_like_mark
            ],
            "units": sorted(self.units),
        }
