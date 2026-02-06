import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, Item, User
from app.models.image import Image


@pytest.mark.asyncio
async def test_create_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a collection."""
    response = await client.post(
        "/collections",
        json={"name": "My Antiques", "description": "Vintage items"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Antiques"
    assert data["description"] == "Vintage items"
    assert data["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_list_collections(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing collections."""
    # Create collections
    collection1 = Collection(user_id=str(test_user.id), name="Collection A")
    collection2 = Collection(user_id=str(test_user.id), name="Collection B")
    session.add_all([collection1, collection2])
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Collection A"  # Ordered alphabetically
    assert data[1]["name"] == "Collection B"


@pytest.mark.asyncio
async def test_list_collections_with_item_count(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that collection listing includes item count."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    # Add items to collection
    item1 = Item(user_id=str(test_user.id), collection_id=collection.id, name="Item 1")
    item2 = Item(user_id=str(test_user.id), collection_id=collection.id, name="Item 2")
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["item_count"] == 2


@pytest.mark.asyncio
async def test_get_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test getting a single collection."""
    collection = Collection(user_id=str(test_user.id), name="My Collection", description="Test")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.get(f"/collections/{collection.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "My Collection"
    assert data["description"] == "Test"
    assert data["item_count"] == 0


@pytest.mark.asyncio
async def test_get_collection_not_found(client: AsyncClient, test_user: User, auth_client):
    """Test getting a non-existent collection."""
    response = await client.get("/collections/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_collection_other_user(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users cannot access other users' collections."""
    collection = Collection(user_id=str(other_user.id), name="Other's Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.get(f"/collections/{collection.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a collection."""
    collection = Collection(user_id=str(test_user.id), name="Original Name")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.patch(
        f"/collections/{collection.id}",
        json={"name": "Updated Name", "description": "New description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "New description"


@pytest.mark.asyncio
async def test_update_collection_partial(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test partial update of a collection."""
    collection = Collection(user_id=str(test_user.id), name="Original", description="Original desc")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.patch(
        f"/collections/{collection.id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["description"] == "Original desc"  # Unchanged


@pytest.mark.asyncio
async def test_delete_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a collection."""
    collection = Collection(user_id=str(test_user.id), name="To Delete")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.delete(f"/collections/{collection.id}")
    assert response.status_code == 204

    # Verify it's deleted
    response = await client.get(f"/collections/{collection.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_collection_items_become_uncategorized(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that items become uncategorized when collection is deleted."""
    collection = Collection(user_id=str(test_user.id), name="To Delete")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    item = Item(user_id=str(test_user.id), collection_id=collection.id, name="My Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(f"/collections/{collection.id}")
    assert response.status_code == 204

    # Check item still exists but has no collection
    await session.refresh(item)
    assert item.collection_id is None


@pytest.mark.asyncio
async def test_create_collection_default_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that collections default to 'general' type."""
    response = await client.post(
        "/collections",
        json={"name": "My Collection"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "general"


@pytest.mark.asyncio
async def test_create_collection_with_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a collection with a specific type."""
    response = await client.post(
        "/collections",
        json={"name": "My Stamps", "type": "stamp"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "stamp"


@pytest.mark.asyncio
async def test_create_collection_invalid_type(client: AsyncClient, test_user: User, auth_client):
    """Test that creating a collection with unknown type returns 422."""
    response = await client.post(
        "/collections",
        json={"name": "Bad Collection", "type": "unknown_type"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_collection_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a collection's type."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.patch(
        f"/collections/{collection.id}",
        json={"type": "stamp"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "stamp"
    assert data["name"] == "My Collection"  # Unchanged


@pytest.mark.asyncio
async def test_update_collection_invalid_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that updating to an unknown type returns 422."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.patch(
        f"/collections/{collection.id}",
        json={"type": "nonexistent"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_collections_includes_type(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that listing collections includes the type field."""
    collection = Collection(user_id=str(test_user.id), name="Stamps", type="stamp")
    session.add(collection)
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "stamp"


@pytest.mark.asyncio
async def test_collections_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users only see their own collections."""
    my_collection = Collection(user_id=str(test_user.id), name="My Collection")
    other_collection = Collection(user_id=str(other_user.id), name="Other Collection")
    session.add_all([my_collection, other_collection])
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Collection"


@pytest.mark.asyncio
async def test_list_collections_preview_images(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that listing collections includes preview images from items."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    # Create items with images
    item1 = Item(user_id=str(test_user.id), collection_id=collection.id, name="Item 1")
    item2 = Item(user_id=str(test_user.id), collection_id=collection.id, name="Item 2")
    session.add_all([item1, item2])
    await session.commit()
    await session.refresh(item1)
    await session.refresh(item2)

    img1 = Image(
        user_id=str(test_user.id),
        item_id=item1.id,
        filename="a.jpg",
        storage_key="key-a",
        url="https://example.com/a.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        position=0,
    )
    img2 = Image(
        user_id=str(test_user.id),
        item_id=item2.id,
        filename="b.jpg",
        storage_key="key-b",
        url="https://example.com/b.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        position=0,
    )
    session.add_all([img1, img2])
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert len(data[0]["preview_images"]) == 2
    urls = {p["url"] for p in data[0]["preview_images"]}
    assert "https://example.com/a.jpg" in urls
    assert "https://example.com/b.jpg" in urls


@pytest.mark.asyncio
async def test_list_collections_preview_images_max_four(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that preview images are limited to 4 per collection."""
    collection = Collection(user_id=str(test_user.id), name="Big Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    # Create 6 items each with an image
    for i in range(6):
        item = Item(user_id=str(test_user.id), collection_id=collection.id, name=f"Item {i}")
        session.add(item)
        await session.commit()
        await session.refresh(item)
        img = Image(
            user_id=str(test_user.id),
            item_id=item.id,
            filename=f"img{i}.jpg",
            storage_key=f"key-{i}",
            url=f"https://example.com/img{i}.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
            position=0,
        )
        session.add(img)
    await session.commit()

    response = await client.get("/collections")
    assert response.status_code == 200
    data = response.json()
    assert len(data[0]["preview_images"]) == 4


@pytest.mark.asyncio
async def test_get_collection_preview_images(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that getting a single collection includes preview images."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    item = Item(user_id=str(test_user.id), collection_id=collection.id, name="Item 1")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    img = Image(
        user_id=str(test_user.id),
        item_id=item.id,
        filename="pic.jpg",
        storage_key="key-pic",
        url="https://example.com/pic.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        position=0,
    )
    session.add(img)
    await session.commit()

    response = await client.get(f"/collections/{collection.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["preview_images"]) == 1
    assert data["preview_images"][0]["url"] == "https://example.com/pic.jpg"


@pytest.mark.asyncio
async def test_collection_no_images_empty_preview(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that collections without images have empty preview_images."""
    collection = Collection(user_id=str(test_user.id), name="Empty Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.get(f"/collections/{collection.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["preview_images"] == []
