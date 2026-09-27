import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Import, Item, User
from tests.catalogit_factory import entries_json, entries_zip, entry, media_csv

ENTRIES = [
    entry("cit-1", **{"Entry/Object ID": "A-01", "Dimensions": {"Height": "3 in"}}),
    entry("cit-2", name="Brooch", **{"Entry/Object ID": "B-01", "Category": "Jewelry"}),
]
MEDIA = [("cit-1", "a.jpg", "Front", ""), ("cit-2", "b.jpg", "", "Hallmark on the pin")]


def _files(entries: bytes, media: bytes | None = None, name: str = "EntryExport-1.zip"):
    files = [("entries", (name, entries, "application/zip"))]
    if media is not None:
        files.append(("media_index", ("media-export-1.csv", media, "text/csv")))
    return files


async def _preview(client: AsyncClient) -> dict:
    response = await client.post(
        "/imports",
        files=_files(entries_zip(ENTRIES), media_csv(MEDIA)),
        data={"source": "catalogit"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_previews_an_export_without_touching_the_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    data = await _preview(client)

    assert data["status"] == "preview"
    assert data["source"] == "catalogit"
    assert data["entries_filename"] == "EntryExport-1.zip"
    assert data["media_index_filename"] == "media-export-1.csv"
    report = data["report"]
    assert report["counts"]["items"] == 2
    assert report["counts"]["photos"] == 2
    assert report["units"] == ["imperial"]
    assert report["groupings"]["reference_prefix"] == [
        {"key": "A", "count": 1},
        {"key": "B", "count": 1},
    ]
    assert [p["filename"] for p in report["photos_that_look_like_marks"]] == ["b.jpg"]
    items = await session.scalar(select(func.count()).select_from(Item))
    assert items == 0


async def test_reads_the_bare_json_and_needs_no_media_index(client: AsyncClient, auth_client):
    response = await client.post(
        "/imports", files=_files(entries_json(ENTRIES), name="export.json")
    )

    assert response.status_code == 201
    assert response.json()["media_index_filename"] is None
    assert response.json()["report"]["counts"]["photos"] == 0


@pytest.mark.parametrize(
    ("entries", "media", "message"),
    [
        (b'{"not": "a list"}', None, "doesn't look like a CatalogIt entries export"),
        (b"", None, "is empty"),
        (entries_json(ENTRIES), b"name\nphoto.jpg\n", "doesn't look like a CatalogIt media index"),
    ],
    ids=["wrong json", "empty", "wrong csv"],
)
async def test_refuses_what_is_not_a_catalogit_export(
    client: AsyncClient, auth_client, entries, media, message
):
    response = await client.post("/imports", files=_files(entries, media))

    assert response.status_code == 400
    assert message in response.json()["detail"]


async def test_refuses_oversized_uploads(
    client: AsyncClient, auth_client, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.routers.imports.MAX_ENTRIES_UPLOAD", 100)

    response = await client.post("/imports", files=_files(entries_json(ENTRIES * 10)))

    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


async def test_lists_and_gets_the_users_imports(client: AsyncClient, auth_client):
    created = await _preview(client)

    listed = (await client.get("/imports")).json()
    fetched = (await client.get(f"/imports/{created['id']}")).json()

    assert [(i["id"], i["counts"]["items"]) for i in listed] == [(created["id"], 2)]
    assert "report" not in listed[0]
    assert fetched["report"] == created["report"]


async def test_discarding_a_preview(client: AsyncClient, auth_client):
    created = await _preview(client)

    assert (await client.delete(f"/imports/{created['id']}")).status_code == 204
    assert (await client.get(f"/imports/{created['id']}")).status_code == 404


async def test_imports_are_private(
    client: AsyncClient, session: AsyncSession, other_user: User, auth_client
):
    theirs = Import(
        user_id=str(other_user.id),
        source="catalogit",
        status="preview",
        entries_filename="theirs.zip",
        report={"counts": {}},
    )
    session.add(theirs)
    await session.commit()

    assert (await client.get(f"/imports/{theirs.id}")).status_code == 404
    assert (await client.delete(f"/imports/{theirs.id}")).status_code == 404
    assert (await client.get("/imports")).json() == []


async def test_requires_authentication(client: AsyncClient):
    assert (await client.get("/imports")).status_code == 401
    assert (await client.post("/imports", files=_files(entries_json(ENTRIES)))).status_code == 401
