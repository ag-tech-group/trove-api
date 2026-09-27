from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, Import, Tag, User
from tests.catalogit_factory import entries_zip, entry, media_csv
from tests.image_factory import make_image

ENTRIES = [
    entry(
        "cit-1",
        **{
            "Entry/Object ID": "A-01",
            "Valuations": {"Value": "$120.00", "Date": "2021"},
            "General Notes": {"Note": "Bought at auction.", "Note Type": "History"},
            "Inscription/Signature/Marks": "Stamped on the base",
        },
    ),
    entry("cit-2", name="Teapot", **{"Entry/Object ID": "a-02"}),
    entry("cit-3", name="Brooch", **{"Entry/Object ID": "B-01", "Category": "Jewelry"}),
    entry("cit-4", name="Lace"),
]
MEDIA = [
    ("cit-1", "a-front.jpg", "Front", ""),
    ("cit-1", "a-base.jpg", "", "The maker's mark on the base"),
    ("cit-3", "b.jpg", "", ""),
]
GROUPED = {
    "grouping": "reference_prefix",
    "groups": {
        "a": {"collection": {"name": "Silver"}, "tags": ["Egypt"]},
        "B": {"collection": {"name": "Jewelry"}, "tags": ["Europe"]},
    },
    "default": {"collection": {"name": "Other"}},
}


@pytest.fixture(autouse=True)
def storage():
    with (
        patch("app.images.upload_file", new_callable=AsyncMock) as upload,
        patch("app.routers.imports.delete_files", new_callable=AsyncMock) as delete_many,
        patch("app.imports.commit.delete_file", new_callable=AsyncMock),
    ):
        upload.side_effect = lambda data, key, content_type: f"https://storage.example/{key}"
        yield SimpleNamespace(upload=upload, delete_many=delete_many)


async def _preview(client: AsyncClient, entries=ENTRIES, media=MEDIA) -> str:
    response = await client.post(
        "/imports",
        files=[
            ("entries", ("export.zip", entries_zip(entries), "application/zip")),
            ("media_index", ("media.csv", media_csv(media), "text/csv")),
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _commit(client: AsyncClient, import_id: str, options=GROUPED) -> dict:
    response = await client.post(f"/imports/{import_id}/commit", json=options)
    assert response.status_code == 200, response.text
    return response.json()


async def _upload(client: AsyncClient, import_id: str, name: str, data: bytes | None = None):
    return await client.post(
        f"/imports/{import_id}/photos",
        files=[("file", (name, make_image() if data is None else data, "image/jpeg"))],
    )


async def _items(client: AsyncClient) -> dict[str, dict]:
    return {item["name"]: item for item in (await client.get("/items")).json()}


async def test_commit_creates_the_items_grouped_and_tagged(client: AsyncClient, auth_client):
    import_id = await _preview(client)

    committed = await _commit(client, import_id)

    assert committed["status"] == "importing"
    assert committed["outcome"] == {"items": 4, "skipped": 0, "photos": 3}
    assert committed["pending_photos"] == ["a-base.jpg", "a-front.jpg", "b.jpg"]
    items = await _items(client)
    assert {name: item["collection_name"] for name, item in items.items()} == {
        "Tea caddy": "Silver",
        "Teapot": "Silver",
        "Brooch": "Jewelry",
        "Lace": "Other",
    }
    assert {tag["name"] for tag in items["Brooch"]["tags"]} == {"Jewelry", "Europe"}
    caddy = items["Tea caddy"]
    assert [t["name"] for t in caddy["tags"]] == ["Egypt"]
    assert [(v["value"], v["valued_on"]) for v in caddy["valuations"]] == [("120.00", "2021")]
    assert caddy["estimated_value"] == "120.00"
    assert [(n["title"], n["body"]) for n in caddy["item_notes"]] == [
        ("History", "Bought at auction.")
    ]
    assert [m["title"] for m in caddy["marks"]] == ["Stamped on the base"]


async def test_commit_reuses_the_accounts_collections_and_tags(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    session.add_all(
        [
            Collection(user_id=str(test_user.id), name="silver"),
            Tag(user_id=str(test_user.id), name="egypt"),
        ]
    )
    await session.commit()

    await _commit(client, await _preview(client))

    collections = (await session.execute(select(Collection.name))).scalars().all()
    tags = (await session.execute(select(Tag.name))).scalars().all()
    assert sorted(collections) == ["Jewelry", "Other", "silver"]
    assert sorted(tags) == ["Europe", "Jewelry", "egypt"]


async def test_commit_refuses_another_accounts_collection_before_writing_anything(
    client: AsyncClient, session: AsyncSession, other_user: User, auth_client
):
    theirs = Collection(user_id=str(other_user.id), name="Theirs")
    session.add(theirs)
    await session.commit()
    import_id = await _preview(client)

    response = await client.post(
        f"/imports/{import_id}/commit", json={"default": {"collection": {"id": theirs.id}}}
    )

    assert response.status_code == 404
    assert (await client.get("/items")).json() == []
    assert (await client.get(f"/imports/{import_id}")).json()["status"] == "preview"


async def test_committing_twice_is_refused(client: AsyncClient, auth_client):
    import_id = await _preview(client)
    await _commit(client, import_id)

    response = await client.post(f"/imports/{import_id}/commit", json={})

    assert response.status_code == 409


async def test_entries_imported_before_are_left_out(client: AsyncClient, auth_client):
    await _commit(client, await _preview(client))

    second = await _preview(client)
    preview = (await client.get(f"/imports/{second}")).json()
    committed = await _commit(client, second)

    assert preview["report"]["already_imported"] == 4
    assert committed["outcome"] == {"items": 0, "skipped": 4, "photos": 0}
    assert committed["status"] == "completed"
    assert len(await _items(client)) == 4


async def test_photos_land_in_catalog_order_whatever_order_they_arrive(
    client: AsyncClient, session: AsyncSession, auth_client
):
    import_id = await _preview(client)
    await _commit(client, import_id)

    for name in ["b.jpg", "a-base.jpg", "a-front.jpg"]:
        response = await _upload(client, import_id, name)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"

    caddy = (await _items(client))["Tea caddy"]
    assert [(i["position"], i["caption"], i["description"]) for i in caddy["images"]] == [
        (0, "Front", None),
        (1, None, "The maker's mark on the base"),
    ]
    assert caddy["images"][0]["width"] == 64
    done = (await client.get(f"/imports/{import_id}")).json()
    assert done["status"] == "completed"
    assert done["photos"] == {"total": 3, "pending": 0, "done": 3, "failed": 0, "skipped": 0}
    source = await session.scalar(select(Import.source_data).where(Import.id == import_id))
    assert source is None


async def test_uploading_a_photo_twice_stores_it_once(client: AsyncClient, auth_client, storage):
    import_id = await _preview(client)
    await _commit(client, import_id)

    first = await _upload(client, import_id, "b.jpg")
    second = await _upload(client, import_id, "b.jpg")

    assert first.json()["image"]["id"] == second.json()["image"]["id"]
    assert storage.upload.await_count == 1


async def test_a_failed_photo_is_reported_and_can_be_sent_again(client: AsyncClient, auth_client):
    import_id = await _preview(client)
    await _commit(client, import_id)

    failed = await _upload(client, import_id, "b.jpg", b"not an image")
    progress = (await client.get(f"/imports/{import_id}")).json()
    retried = await _upload(client, import_id, "b.jpg")

    assert failed.status_code == 400
    assert progress["photos"]["failed"] == 1
    assert progress["failed_photos"][0]["filename"] == "b.jpg"
    assert "Not a valid" in progress["failed_photos"][0]["error"]
    assert retried.json()["status"] == "done"


@pytest.mark.parametrize(
    ("commit_first", "name", "expected"),
    [(True, "unknown.jpg", 404), (False, "b.jpg", 409)],
    ids=["not expected", "not committed"],
)
async def test_uploads_the_import_is_not_waiting_for_are_refused(
    client: AsyncClient, auth_client, commit_first, name, expected
):
    import_id = await _preview(client)
    if commit_first:
        await _commit(client, import_id)

    assert (await _upload(client, import_id, name)).status_code == expected


async def test_photos_chosen_as_marks_go_on_a_new_mark(client: AsyncClient, auth_client):
    import_id = await _preview(client)
    await _commit(client, import_id, {**GROUPED, "mark_photos": ["A-BASE.jpg"]})

    await _upload(client, import_id, "a-base.jpg")

    caddy = (await _items(client))["Tea caddy"]
    marks = {mark["title"]: mark for mark in caddy["marks"]}
    assert set(marks) == {"Stamped on the base", "The maker's mark on the base"}
    (image,) = marks["The maker's mark on the base"]["images"]
    assert image["description"] == "The maker's mark on the base"
    assert [i["caption"] for i in caddy["images"]] == []


async def test_finishing_skips_what_has_not_arrived(client: AsyncClient, auth_client):
    import_id = await _preview(client)
    await _commit(client, import_id)
    await _upload(client, import_id, "b.jpg")

    finished = (await client.post(f"/imports/{import_id}/finish")).json()

    assert finished["status"] == "completed"
    assert finished["photos"] == {"total": 3, "pending": 0, "done": 1, "failed": 0, "skipped": 2}
    assert (await _upload(client, import_id, "a-front.jpg")).status_code == 409


async def test_undo_removes_what_the_import_created_and_nothing_else(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, storage
):
    session.add(Tag(user_id=str(test_user.id), name="Europe"))
    await session.commit()
    import_id = await _preview(client)
    await _commit(client, import_id, {**GROUPED, "mark_photos": ["a-base.jpg"]})
    await _upload(client, import_id, "a-front.jpg")
    await _upload(client, import_id, "a-base.jpg")

    assert (await client.delete(f"/imports/{import_id}")).status_code == 204

    assert (await client.get("/items")).json() == []
    assert (await session.execute(select(Collection))).scalars().all() == []
    assert (await session.execute(select(Tag.name))).scalars().all() == ["Europe"]
    (keys,) = storage.delete_many.await_args.args
    assert len(keys) == 2
    assert any(key.startswith("marks/") for key in keys)
    assert (await client.get(f"/imports/{import_id}")).status_code == 404


async def test_undo_keeps_collections_and_tags_something_else_uses(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    import_id = await _preview(client)
    await _commit(client, import_id)
    silver = await session.scalar(select(Collection).where(Collection.name == "Silver"))
    egypt = await session.scalar(select(Tag).where(Tag.name == "Egypt"))
    await client.post(
        "/items", json={"name": "Mine", "collection_id": silver.id, "tag_ids": [egypt.id]}
    )

    await client.delete(f"/imports/{import_id}")

    assert list(await _items(client)) == ["Mine"]
    assert (await session.execute(select(Collection.name))).scalars().all() == ["Silver"]
    assert (await session.execute(select(Tag.name))).scalars().all() == ["Egypt"]


async def test_undo_after_the_owner_deleted_an_imported_item(client: AsyncClient, auth_client):
    import_id = await _preview(client)
    await _commit(client, import_id)
    teapot = (await _items(client))["Teapot"]
    await client.delete(f"/items/{teapot['id']}")

    assert (await client.delete(f"/imports/{import_id}")).status_code == 204
    assert (await client.get("/items")).json() == []


async def test_other_accounts_cannot_act_on_an_import(
    client: AsyncClient, session: AsyncSession, other_user: User, auth_client
):
    theirs = Import(
        user_id=str(other_user.id),
        source="catalogit",
        status="importing",
        entries_filename="theirs.zip",
        report={"counts": {}},
    )
    session.add(theirs)
    await session.commit()

    assert (await client.post(f"/imports/{theirs.id}/commit", json={})).status_code == 404
    assert (await _upload(client, theirs.id, "b.jpg")).status_code == 404
    assert (await client.post(f"/imports/{theirs.id}/finish")).status_code == 404
    assert (await client.delete(f"/imports/{theirs.id}")).status_code == 404


async def test_deleting_an_item_clears_its_marks_images_from_storage(
    client: AsyncClient, session: AsyncSession, auth_client
):
    import_id = await _preview(client)
    await _commit(client, import_id, {**GROUPED, "mark_photos": ["a-base.jpg"]})
    await _upload(client, import_id, "a-front.jpg")
    await _upload(client, import_id, "a-base.jpg")
    caddy = (await _items(client))["Tea caddy"]

    with patch("app.routers.items.delete_files", new_callable=AsyncMock) as delete_many:
        await client.delete(f"/items/{caddy['id']}")

    (keys,) = delete_many.await_args.args
    assert sorted(key.split("/")[0] for key in keys) == ["items", "marks"]
