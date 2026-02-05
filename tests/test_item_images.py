from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User
from app.models.image import Image


def _fake_file(content_type="image/jpeg", size=100, filename="test.jpg"):
    """Create a fake file tuple for upload."""
    data = b"x" * size
    return ("file", (filename, BytesIO(data), content_type))


@pytest.fixture(autouse=True)
def mock_storage():
    """Mock R2 storage calls for all tests in this module."""
    with (
        patch("app.routers.item_images.upload_file", new_callable=AsyncMock) as mock_upload,
        patch("app.routers.item_images.delete_file", new_callable=AsyncMock),
        patch("app.routers.items.delete_files", new_callable=AsyncMock),
    ):
        mock_upload.return_value = "https://r2.example.com/test-key"
        yield


@pytest.mark.asyncio
async def test_list_item_images_empty(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing images on an item with none."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}/images")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_upload_item_image(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test uploading an image to an item."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/images",
        files=[_fake_file()],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["item_id"] == item.id
    assert data["mark_id"] is None
    assert data["filename"] == "test.jpg"
    assert data["content_type"] == "image/jpeg"
    assert data["size_bytes"] == 100
    assert data["position"] == 0
    assert data["url"] == "https://r2.example.com/test-key"


@pytest.mark.asyncio
async def test_upload_item_image_increments_position(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that position increments with each upload."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    r1 = await client.post(f"/items/{item.id}/images", files=[_fake_file()])
    r2 = await client.post(f"/items/{item.id}/images", files=[_fake_file(filename="test2.jpg")])
    assert r1.json()["position"] == 0
    assert r2.json()["position"] == 1


@pytest.mark.asyncio
async def test_upload_item_image_invalid_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that non-image files are rejected."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/images",
        files=[_fake_file(content_type="application/pdf", filename="doc.pdf")],
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_item_image_too_large(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that files exceeding 10MB are rejected."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/images",
        files=[_fake_file(size=11 * 1024 * 1024)],
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_item_image_max_count(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that uploading beyond 10 images is rejected."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    # Create 10 images directly in DB
    for i in range(10):
        img = Image(
            user_id=str(test_user.id),
            item_id=item.id,
            filename=f"img{i}.jpg",
            storage_key=f"items/{item.id}/img{i}.jpg",
            url=f"https://r2.example.com/img{i}.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            position=i,
        )
        session.add(img)
    await session.commit()

    response = await client.post(
        f"/items/{item.id}/images",
        files=[_fake_file()],
    )
    assert response.status_code == 400
    assert "Maximum" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_item_image(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting an image from an item."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    img = Image(
        user_id=str(test_user.id),
        item_id=item.id,
        filename="test.jpg",
        storage_key=f"items/{item.id}/test.jpg",
        url="https://r2.example.com/test.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        position=0,
    )
    session.add(img)
    await session.commit()
    await session.refresh(img)

    response = await client.delete(f"/items/{item.id}/images/{img.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/images")
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_item_image_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a non-existent image returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(f"/items/{item.id}/images/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_item_images_user_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that images on another user's item are inaccessible."""
    other_item = Item(user_id=str(other_user.id), name="Other Item")
    session.add(other_item)
    await session.commit()
    await session.refresh(other_item)

    response = await client.get(f"/items/{other_item.id}/images")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_item_images_in_item_response(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that images are included in the item detail response."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    img = Image(
        user_id=str(test_user.id),
        item_id=item.id,
        filename="test.jpg",
        storage_key=f"items/{item.id}/test.jpg",
        url="https://r2.example.com/test.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        position=0,
    )
    session.add(img)
    await session.commit()

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["images"]) == 1
    assert data["images"][0]["filename"] == "test.jpg"


@pytest.mark.asyncio
async def test_upload_png_and_webp(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that PNG and WebP files are accepted."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    for ct, fn in [("image/png", "img.png"), ("image/webp", "img.webp")]:
        response = await client.post(
            f"/items/{item.id}/images",
            files=[_fake_file(content_type=ct, filename=fn)],
        )
        assert response.status_code == 201
        assert response.json()["content_type"] == ct
