from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User
from app.models.image import Image
from app.models.mark import Mark


def _fake_file(content_type="image/jpeg", size=100, filename="test.jpg"):
    """Create a fake file tuple for upload."""
    data = b"x" * size
    return ("file", (filename, BytesIO(data), content_type))


@pytest.fixture(autouse=True)
def mock_storage():
    """Mock R2 storage calls for all tests in this module."""
    with (
        patch("app.routers.mark_images.upload_file", new_callable=AsyncMock) as mock_upload,
        patch("app.routers.mark_images.delete_file", new_callable=AsyncMock),
        patch("app.routers.marks.delete_files", new_callable=AsyncMock),
    ):
        mock_upload.return_value = "https://r2.example.com/test-key"
        yield


@pytest.fixture
async def item_and_mark(session: AsyncSession, test_user: User):
    """Create an item with a mark for testing."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    mark = Mark(item_id=item.id, title="Test Mark")
    session.add(mark)
    await session.commit()
    await session.refresh(mark)

    return item, mark


@pytest.mark.asyncio
async def test_list_mark_images_empty(
    client: AsyncClient, test_user: User, auth_client, item_and_mark
):
    """Test listing images on a mark with none."""
    item, mark = item_and_mark
    response = await client.get(f"/items/{item.id}/marks/{mark.id}/images")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_upload_mark_image(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, item_and_mark
):
    """Test uploading an image to a mark."""
    item, mark = item_and_mark

    response = await client.post(
        f"/items/{item.id}/marks/{mark.id}/images",
        files=[_fake_file()],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mark_id"] == mark.id
    assert data["item_id"] is None
    assert data["filename"] == "test.jpg"
    assert data["content_type"] == "image/jpeg"
    assert data["size_bytes"] == 100
    assert data["position"] == 0


@pytest.mark.asyncio
async def test_upload_mark_image_max_count(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, item_and_mark
):
    """Test that uploading beyond 3 images per mark is rejected."""
    item, mark = item_and_mark

    # Create 3 images directly in DB
    for i in range(3):
        img = Image(
            user_id=str(test_user.id),
            mark_id=mark.id,
            filename=f"img{i}.jpg",
            storage_key=f"marks/{mark.id}/img{i}.jpg",
            url=f"https://r2.example.com/img{i}.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            position=i,
        )
        session.add(img)
    await session.commit()

    response = await client.post(
        f"/items/{item.id}/marks/{mark.id}/images",
        files=[_fake_file()],
    )
    assert response.status_code == 400
    assert "Maximum" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_mark_image_invalid_type(
    client: AsyncClient, test_user: User, auth_client, item_and_mark
):
    """Test that non-image files are rejected on marks."""
    item, mark = item_and_mark

    response = await client.post(
        f"/items/{item.id}/marks/{mark.id}/images",
        files=[_fake_file(content_type="application/pdf", filename="doc.pdf")],
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_mark_image(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, item_and_mark
):
    """Test deleting an image from a mark."""
    item, mark = item_and_mark

    img = Image(
        user_id=str(test_user.id),
        mark_id=mark.id,
        filename="test.jpg",
        storage_key=f"marks/{mark.id}/test.jpg",
        url="https://r2.example.com/test.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        position=0,
    )
    session.add(img)
    await session.commit()
    await session.refresh(img)

    response = await client.delete(f"/items/{item.id}/marks/{mark.id}/images/{img.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/marks/{mark.id}/images")
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_mark_image_not_found(
    client: AsyncClient, test_user: User, auth_client, item_and_mark
):
    """Test deleting a non-existent mark image returns 404."""
    item, mark = item_and_mark

    response = await client.delete(
        f"/items/{item.id}/marks/{mark.id}/images/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_images_user_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that mark images on another user's item are inaccessible."""
    other_item = Item(user_id=str(other_user.id), name="Other Item")
    session.add(other_item)
    await session.commit()
    await session.refresh(other_item)

    other_mark = Mark(item_id=other_item.id, title="Other Mark")
    session.add(other_mark)
    await session.commit()
    await session.refresh(other_mark)

    response = await client.get(f"/items/{other_item.id}/marks/{other_mark.id}/images")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_images_on_nonexistent_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test accessing images on a nonexistent mark returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(
        f"/items/{item.id}/marks/00000000-0000-0000-0000-000000000000/images"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_images_in_mark_response(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, item_and_mark
):
    """Test that images are included in the mark detail response."""
    item, mark = item_and_mark

    img = Image(
        user_id=str(test_user.id),
        mark_id=mark.id,
        filename="test.jpg",
        storage_key=f"marks/{mark.id}/test.jpg",
        url="https://r2.example.com/test.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        position=0,
    )
    session.add(img)
    await session.commit()

    response = await client.get(f"/items/{item.id}/marks")
    assert response.status_code == 200
    marks = response.json()
    assert len(marks) == 1
    assert len(marks[0]["images"]) == 1
    assert marks[0]["images"][0]["filename"] == "test.jpg"
