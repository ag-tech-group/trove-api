"""CatalogIt exports, read into an ImportPlan.

CatalogIt exports entries as JSON (a zip holding one file) and photos as zips of
images with a CSV index; the photos are uploaded one at a time after commit, so only
the index is read here. An entry is an object keyed by CatalogIt's field labels, and
any value may be a string, a list of strings, an object of further fields, or a list
of such objects: every reader below accepts all four.

Whatever has no Trove column is kept as a note titled with its CatalogIt section, so
nothing an owner recorded is dropped. What cannot be read with confidence (a price in
another currency, "circa 1900" as an acquisition date) stays text in those notes too.
"""

import csv
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from typing import Any

from app.image_utils import MAX_ITEM_IMAGES
from app.imports.plan import (
    FieldUse,
    ImportIssue,
    ImportPlan,
    PlannedItem,
    PlannedMark,
    PlannedNote,
    PlannedPhoto,
    PlannedValuation,
)
from app.imports.values import (
    IMPERIAL_UNITS,
    clip,
    parse_length,
    parse_money,
    parse_partial_date,
    parse_weight,
    records,
    texts,
)

MAX_ENTRIES = 5000
# Uncompressed, across every JSON file in the export.
MAX_ENTRIES_BYTES = 50 * 1024 * 1024


class ImportFileError(ValueError):
    """An uploaded file that isn't what the import expects, in words for its owner."""


def read_entries(data: bytes) -> list[dict]:
    """The entries in a CatalogIt entries export: the zip as downloaded, or its JSON."""
    documents = _json_documents(data)
    entries: list[dict] = []
    for document in documents:
        try:
            parsed = json.loads(document.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ImportFileError("The entries export isn't readable JSON.") from exc
        if not isinstance(parsed, list) or not all(isinstance(e, dict) for e in parsed):
            raise ImportFileError("That file doesn't look like a CatalogIt entries export.")
        entries.extend(parsed)
    if not any("CIT ID" in entry for entry in entries):
        raise ImportFileError("That file doesn't look like a CatalogIt entries export.")
    if len(entries) > MAX_ENTRIES:
        raise ImportFileError(f"An import can hold up to {MAX_ENTRIES} entries.")
    return entries


def _json_documents(data: bytes) -> list[bytes]:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return [data]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [
                member
                for member in archive.infolist()
                if not member.is_dir() and member.filename.lower().endswith(".json")
            ]
            if not members:
                raise ImportFileError("The zip holds no JSON file.")
            # Declared sizes bound what reading returns, so a zip claiming little and
            # inflating to much stops here rather than in memory.
            if sum(member.file_size for member in members) > MAX_ENTRIES_BYTES:
                raise ImportFileError("The entries export is too large to import.")
            return [archive.read(member) for member in members]
    except zipfile.BadZipFile as exc:
        raise ImportFileError("The entries zip is damaged.") from exc


def read_media_index(data: bytes) -> list[dict[str, str]]:
    """The rows of a CatalogIt media index CSV, cut down to what the import uses."""
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        if not reader.fieldnames or not {"uuid", "Image File"} <= set(reader.fieldnames):
            raise ImportFileError("That file doesn't look like a CatalogIt media index.")
        return [
            {
                "entry": (row.get("uuid") or "").strip(),
                "path": (row.get("Image File") or "").strip(),
                "caption": (row.get("Caption") or "").strip(),
                "description": (row.get("Description") or "").strip(),
            }
            for row in reader
        ]
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ImportFileError("The media index isn't a readable CSV file.") from exc


def plan_import(entries: list[dict], media: list[dict[str, str]]) -> ImportPlan:
    fields = FieldUse()
    issues: list[ImportIssue] = []
    units: set[str] = set()
    photos = _photos(media, fields, issues)

    items: list[PlannedItem] = []
    seen: set[str] = set()
    for raw in entries:
        item = _Entry(raw, fields, issues, units).plan()
        if item is None:
            continue
        if item.external_id in seen:
            issues.append(
                ImportIssue("duplicate_entry", "Listed twice; imported once.", item.label)
            )
            continue
        seen.add(item.external_id)
        item.photos = photos.pop(item.external_id, [])
        if len(item.photos) > MAX_ITEM_IMAGES:
            issues.append(
                ImportIssue(
                    "too_many_photos",
                    f"Has {len(item.photos)} photos; the first {MAX_ITEM_IMAGES} are imported.",
                    item.label,
                )
            )
            del item.photos[MAX_ITEM_IMAGES:]
        items.append(item)

    for entry_photos in photos.values():
        for photo in entry_photos:
            issues.append(
                ImportIssue(
                    "photo_without_entry",
                    "The media index lists this photo for an entry that isn't in the export.",
                    photo.filename,
                )
            )
    references = Counter(
        i.fields["reference_number"] for i in items if "reference_number" in i.fields
    )
    for reference, count in sorted(references.items()):
        if count > 1:
            issues.append(
                ImportIssue("shared_reference", f"{count} entries share this number.", reference)
            )
    return ImportPlan(items=items, issues=issues, fields=fields, units=units, entries=len(entries))


_MARK_WORDS = re.compile(
    r"\b(hallmarks?|marks?|marked|maker'?s mark|signature|signed|seals?|stamp(?:ed|s)?|"
    r"inscri\w*|monogram)\b",
    re.I,
)


def _photos(
    rows: list[dict[str, str]], fields: FieldUse, issues: list[ImportIssue]
) -> dict[str, list[PlannedPhoto]]:
    by_entry: dict[str, list[PlannedPhoto]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        filename = re.split(r"[\\/]", row["path"])[-1]
        if not row["entry"] or not filename:
            continue
        # Uploads are matched on the file's own name, so it has to be unique.
        if filename.casefold() in seen:
            issues.append(ImportIssue("duplicate_photo", "Listed twice; imported once.", filename))
            continue
        seen.add(filename.casefold())

        caption, description = row["caption"] or None, row["description"] or None
        if caption:
            shortened, cut = clip(caption, 500)
            if cut:
                description = "\n\n".join(filter(None, [caption, description]))
                caption = shortened
            fields.record("Media › Caption", "photo caption")
        if description:
            fields.record("Media › Description", "photo description")
        by_entry[row["entry"]].append(
            PlannedPhoto(
                path=row["path"],
                filename=filename,
                caption=caption,
                description=description,
                looks_like_mark=bool(_MARK_WORDS.search(f"{caption or ''} {description or ''}")),
            )
        )
    return by_entry


# CatalogIt's own bookkeeping: when the entry was typed, and by whom. The "by whom"
# is a person's name, and none of it describes the object.
_IGNORED = {"Create Date", "Created By", "Update Date", "Updated By"}
_TAG_FIELDS = {"Category", "Item Type", "Style"}
_HANDLED = {"CIT ID", "Name/Title", "Entry/Object ID", "Description"}

_METHODS = {
    "bought": "purchase",
    "purchase": "purchase",
    "purchased": "purchase",
    "gift": "gift",
    "gifted": "gift",
    "donation": "gift",
    "donated": "gift",
    "inherited": "inheritance",
    "inheritance": "inheritance",
    "bequest": "inheritance",
    "bequeathed": "inheritance",
    "trade": "trade",
    "traded": "trade",
    "exchange": "trade",
    "commission": "commission",
    "commissioned": "commission",
}
_CONDITIONS = {
    "mint": "excellent",
    "excellent": "excellent",
    "as new": "excellent",
    "very good": "good",
    "good": "good",
    "fair": "fair",
    "worn": "fair",
    "poor": "poor",
    "damaged": "poor",
}
_LENGTHS = {
    "Height": "height_cm",
    "Width": "width_cm",
    "Depth": "depth_cm",
    "Length": "length_cm",
    "Diameter": "diameter_cm",
}


def _is_tag_field(key: str) -> bool:
    return key in _TAG_FIELDS or key.startswith("Type of ") or key.endswith(" Type")


def _reference_prefix(reference: str) -> str | None:
    """ "J-Eu-12" -> "J-Eu", "2019.001.003" -> "2019.001": the number without its count."""
    return re.sub(r"\d+[a-z]?\W*$", "", reference, flags=re.I).rstrip(" -_./") or None


class _Entry:
    """One CatalogIt entry, planned field by field."""

    def __init__(
        self, raw: dict, fields: FieldUse, issues: list[ImportIssue], units: set[str]
    ) -> None:
        self.raw = raw
        self.fields = fields
        self.issues = issues
        self.units = units
        self.columns: dict[str, Any] = {}
        self.tags: list[str] = []
        self.notes: dict[str, list[str]] = {}
        self.marks: list[PlannedMark] = []
        self.valuations: list[PlannedValuation] = []
        self.label: str | None = None

    def plan(self) -> PlannedItem | None:
        raw = self.raw
        external_id = next(iter(texts(raw.get("CIT ID"))), None)
        reference = next(iter(texts(raw.get("Entry/Object ID"))), None)
        names = texts(raw.get("Name/Title"))
        self.label = reference or (names[0] if names else None)
        if not external_id:
            self._issue("no_id", "An entry without a CatalogIt ID was skipped.")
            return None
        self.fields.record("CIT ID", "import id")

        if names:
            self._set("name", names[0], 200, "Name/Title")
        else:
            self.columns["name"] = reference or "Untitled"
            self._issue("no_name", f"Has no name, so it is called {self.columns['name']!r}.")
        if reference:
            self._set("reference_number", reference, 100, "Entry/Object ID")
        if description := "\n\n".join(texts(raw.get("Description"))):
            self._set("description", description, 5000, "Description")

        for key, value in raw.items():
            if key in _HANDLED:
                continue
            if key in _IGNORED:
                self.fields.record(key, "not imported")
            elif _is_tag_field(key):
                self._tags(key, value)
            elif handler := _GROUP_HANDLERS.get(key):
                handler(self, key, value)
            elif records(value):
                self._note_group(key, value)
            else:
                self._note_value("Other details", key, value, key)

        if self.valuations:
            dated = [v for v in self.valuations if v.valued_on]
            latest = max(dated, key=lambda v: v.valued_on) if dated else self.valuations[-1]
            self.columns["estimated_value"] = latest.value

        groups = {}
        if reference and (prefix := _reference_prefix(reference)):
            groups["reference_prefix"] = prefix
        if categories := texts(raw.get("Category")):
            groups["category"] = categories[0]

        return PlannedItem(
            external_id=external_id,
            fields=self.columns,
            tags=self.tags,
            notes=[PlannedNote(title, "\n".join(lines)) for title, lines in self.notes.items()],
            marks=self.marks,
            valuations=self.valuations,
            groups=groups,
        )

    # ── recording ────────────────────────────────────────────────────────────

    def _issue(self, code: str, message: str) -> None:
        self.issues.append(ImportIssue(code, message, self.label))

    def _set(self, column: str, text: str, limit: int, source: str) -> None:
        value, cut = clip(text, limit)
        self.columns[column] = value
        self.fields.record(source, column)
        if cut:
            self.notes.setdefault(source, []).append(text)
            self._issue("shortened", f"{source} was too long, so the full text is in a note.")

    def _note_value(self, title: str, label: str, value: Any, source: str) -> None:
        lines = _lines(label, value)
        for line_label, text in lines:
            self.notes.setdefault(title, []).append(f"{line_label}: {text}")
        if lines:
            self.fields.record(source, f"note: {title}")

    def _note_group(self, group: str, value: Any) -> None:
        for record in records(value):
            for field, raw in record.items():
                self._note_value(group, field, raw, f"{group} › {field}")

    def _unread(self, group: str, field: str, text: str) -> None:
        self._note_value(group, field, text, f"{group} › {field}")
        self._issue(
            "unread_value", f"{group} › {field} {text!r} couldn't be read, so it's kept in a note."
        )

    # ── fields ───────────────────────────────────────────────────────────────

    def _tags(self, key: str, value: Any) -> None:
        for text in texts(value):
            tag, _ = clip(text, 100)
            if tag.casefold() not in {t.casefold() for t in self.tags}:
                self.tags.append(tag)
            self.fields.record(key, "tag")

    def _acquisition(self, group: str, value: Any) -> None:
        for index, record in enumerate(records(value)):
            for field, raw in record.items():
                source = f"{group} › {field}"
                joined = "; ".join(texts(raw))
                if index or records(raw) or not joined:
                    self._note_value(group, field, raw, source)
                elif field == "Acquired From":
                    self._set("acquisition_source", joined, 200, source)
                elif field == "Place":
                    self._set("acquisition_place", joined, 200, source)
                elif field == "Acquisition Method":
                    if method := _METHODS.get(joined.casefold()):
                        self.columns["acquisition_method"] = method
                        self.fields.record(source, "acquisition_method")
                    else:
                        self._note_value(group, field, joined, source)
                elif field == "Amount Paid":
                    if (price := parse_money(joined)) is not None:
                        self.columns["acquisition_price"] = price
                        self.fields.record(source, "acquisition_price")
                    else:
                        self._unread(group, field, joined)
                elif field == "Date":
                    if when := parse_partial_date(joined):
                        self.columns["acquisition_date"] = when
                        self.fields.record(source, "acquisition_date")
                    else:
                        self._note_value(group, field, joined, source)
                else:
                    self._note_value(group, field, raw, source)

    def _dimensions(self, group: str, value: Any) -> None:
        for index, record in enumerate(records(value)):
            for field, raw in record.items():
                source = f"{group} › {field}"
                joined = "; ".join(texts(raw))
                column = _LENGTHS.get(field) or ("weight_kg" if field == "Weight" else None)
                if index or not column or not joined or records(raw):
                    self._note_value(group, field, raw, source)
                    continue
                parsed = parse_weight(joined) if column == "weight_kg" else parse_length(joined)
                if parsed is None:
                    self._unread(group, field, joined)
                    continue
                self.columns[column], unit = parsed
                self.units.add("imperial" if unit in IMPERIAL_UNITS else "metric")
                self.fields.record(source, column)

    def _valuations(self, group: str, value: Any) -> None:
        for record in records(value):
            for field, raw in record.items():
                if records(raw):
                    self._note_value(group, field, raw, f"{group} › {field}")
            fields = {field: "; ".join(texts(raw)) for field, raw in record.items()}
            amount = parse_money(fields.get("Value", ""))
            if amount is None:
                for field, raw in record.items():
                    self._note_value(group, field, raw, f"{group} › {field}")
                self._issue(
                    "unread_value", "A valuation without a readable value is kept in a note."
                )
                continue
            notes = [fields.get("Notes", "")]
            valued_on = None
            if fields.get("Date"):
                valued_on = parse_partial_date(fields["Date"])
                if not valued_on:
                    notes.append(f"Date: {fields['Date']}")
            notes += [
                f"{field}: {text}"
                for field, text in fields.items()
                if text and field not in {"Value", "Date", "Estimator", "Valuation Type", "Notes"}
            ]
            self.valuations.append(
                PlannedValuation(
                    value=amount,
                    valued_on=valued_on,
                    appraiser=clip(fields["Estimator"], 200)[0]
                    if fields.get("Estimator")
                    else None,
                    valuation_type=clip(fields["Valuation Type"], 100)[0]
                    if fields.get("Valuation Type")
                    else None,
                    notes="\n".join(filter(None, notes)) or None,
                )
            )
            for field, text in fields.items():
                if text:
                    self.fields.record(f"{group} › {field}", "valuation")

    def _made(self, group: str, value: Any) -> None:
        found: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for record in records(value):
            for field, raw in record.items():
                source = f"{group} › {field}"
                if field == "Artist Information":
                    for info in records(raw):
                        for sub, sub_raw in info.items():
                            if sub == "Artist":
                                found["artist"] += [
                                    (t, f"{source} › {sub}") for t in texts(sub_raw)
                                ]
                            else:
                                self._note_value(
                                    group, f"{field} › {sub}", sub_raw, f"{source} › {sub}"
                                )
                elif field in (
                    "Manufacturer",
                    "Date made",
                    "Time Period",
                    "Place",
                    "Place of Origin",
                ):
                    found[field] += [(t, source) for t in texts(raw)]
                else:
                    self._note_value(group, field, raw, source)

        makers = found["artist"] or found["Manufacturer"]
        self._assign("artist_maker", 200, makers)
        if found["artist"]:
            self._leftover(group, "Manufacturer", found["Manufacturer"])
        self._assign("date_era", 100, found["Date made"] or found["Time Period"])
        if found["Date made"]:
            self._leftover(group, "Time Period", found["Time Period"])
        places = found["Place of Origin"] + found["Place"]
        self._assign("origin", 200, places)

    def _assign(self, column: str, limit: int, found: list[tuple[str, str]]) -> None:
        if not found:
            return
        self._set(column, "; ".join(text for text, _ in found), limit, found[0][1])
        for _, source in found[1:]:
            self.fields.record(source, column)

    def _leftover(self, group: str, field: str, found: list[tuple[str, str]]) -> None:
        for text, source in found:
            self._note_value(group, field, text, source)

    def _materials(self, group: str, value: Any) -> None:
        found = []
        for record in records(value):
            for field, raw in record.items():
                if field == "Material" and not records(raw):
                    found += [(t, f"{group} › {field}") for t in texts(raw)]
                else:
                    self._note_value(group, field, raw, f"{group} › {field}")
        self._append_materials(found)

    def _artwork(self, group: str, value: Any) -> None:
        found = []
        for record in records(value):
            for field, raw in record.items():
                if field == "Medium" and not records(raw):
                    found += [(t, f"{group} › {field}") for t in texts(raw)]
                else:
                    self._note_value(group, field, raw, f"{group} › {field}")
        self._append_materials(found)

    def _append_materials(self, found: list[tuple[str, str]]) -> None:
        if not found:
            return
        existing = [self.columns["materials"]] if "materials" in self.columns else []
        self._set("materials", "; ".join(existing + [t for t, _ in found]), 500, found[0][1])
        for _, source in found[1:]:
            self.fields.record(source, "materials")

    def _condition(self, group: str, value: Any) -> None:
        for index, record in enumerate(records(value)):
            for field, raw in record.items():
                source = f"{group} › {field}"
                joined = "; ".join(texts(raw))
                condition = _CONDITIONS.get(joined.casefold())
                if field == "Overall Condition" and not index and condition:
                    self.columns["condition"] = condition
                    self.fields.record(source, "condition")
                else:
                    self._note_value(group, field, raw, source)

    def _location(self, group: str, value: Any) -> None:
        for index, record in enumerate(records(value)):
            for field, raw in record.items():
                source = f"{group} › {field}"
                joined = "; ".join(texts(raw))
                if field == "Location" and not index and joined and not records(raw):
                    self._set("location", joined, 200, source)
                else:
                    self._note_value(group, field, raw, source)

    def _general_notes(self, group: str, value: Any) -> None:
        for record in records(value):
            body = "\n\n".join(texts(record.get("Note")))
            if not body:
                continue
            title = next(iter(texts(record.get("Note Type"))), None) or "Note"
            self.notes.setdefault(clip(title, 200)[0], []).append(body)
            self.fields.record(f"{group} › Note", "note")
            for field, raw in record.items():
                if field not in ("Note", "Note Type"):
                    self._note_value(group, field, raw, f"{group} › {field}")

    def _inscriptions(self, key: str, value: Any) -> None:
        for text in texts(value):
            first_line = text.splitlines()[0].strip()
            title, cut = clip(first_line, 200)
            self.marks.append(
                PlannedMark(title=title, description=text if cut or text != first_line else None)
            )
            self.fields.record(key, "mark")

    def _links(self, key: str, value: Any) -> None:
        self._note_value("Links", key, value, key)


_GROUP_HANDLERS = {
    "Acquisition": _Entry._acquisition,
    "Dimensions": _Entry._dimensions,
    "Valuations": _Entry._valuations,
    "Made/Created": _Entry._made,
    "Materials": _Entry._materials,
    "Artwork Details": _Entry._artwork,
    "Condition": _Entry._condition,
    "Location": _Entry._location,
    "General Notes": _Entry._general_notes,
    "Inscription/Signature/Marks": _Entry._inscriptions,
    "Web Links and URLs": _Entry._links,
}


def _lines(label: str, value: Any) -> list[tuple[str, str]]:
    """Every value inside `value` as (label, text), nested labels joined with ›."""
    lines = [(label, text) for text in texts(value)]
    for record in records(value):
        for field, raw in record.items():
            lines += _lines(f"{label} › {field}", raw)
    return lines
