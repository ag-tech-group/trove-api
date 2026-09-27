"""Synthetic CatalogIt exports, shaped like the real ones and holding nothing real."""

import csv
import io
import json
import zipfile


def entry(cit_id: str = "cit-1", name: str | None = "Tea caddy", **fields) -> dict:
    """An entry keyed by CatalogIt's labels. Pass labels with spaces or slashes via **{...}."""
    return {"CIT ID": cit_id, **({"Name/Title": name} if name else {}), **fields}


def entries_json(entries: list[dict]) -> bytes:
    return json.dumps(entries).encode()


def entries_zip(entries: list[dict]) -> bytes:
    """The entries export as CatalogIt downloads it: a zip holding one JSON file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("0f3c-export.json", entries_json(entries))
    return buffer.getvalue()


def media_csv(rows: list[tuple[str, str, str, str]]) -> bytes:
    """A media index, from (entry CIT ID, file name, caption, description) rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "uuid",
            "Object Id",
            "Image File",
            "Caption",
            "Description",
            "Content Type",
            "Size",
            "Size (sortable)",
        ]
    )
    for cit_id, filename, caption, description in rows:
        writer.writerow(
            [
                cit_id,
                "",
                f"media-export-1/{filename}",
                caption,
                description,
                "image/jpeg",
                "1 MB",
                1,
            ]
        )
    return buffer.getvalue().encode()
