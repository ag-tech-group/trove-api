import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, Item, Tag, User


@pytest.mark.asyncio
async def test_create_item(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating an item."""
    response = await client.post(
        "/items",
        json={
            "name": "Vintage Clock",
            "description": "A beautiful antique clock",
            "condition": "good",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Vintage Clock"
    assert data["description"] == "A beautiful antique clock"
    assert data["condition"] == "good"
    assert data["user_id"] == str(test_user.id)
    assert data["tags"] == []


@pytest.mark.asyncio
async def test_create_item_with_tags(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating an item with tags."""
    tag1 = Tag(user_id=str(test_user.id), name="Art")
    tag2 = Tag(user_id=str(test_user.id), name="Vintage")
    session.add_all([tag1, tag2])
    await session.commit()
    await session.refresh(tag1)
    await session.refresh(tag2)

    response = await client.post(
        "/items",
        json={
            "name": "Old Painting",
            "tag_ids": [tag1.id, tag2.id],
        },
    )
    assert response.status_code == 201
    data = response.json()
    tag_names = sorted(t["name"] for t in data["tags"])
    assert tag_names == ["Art", "Vintage"]


@pytest.mark.asyncio
async def test_create_item_with_invalid_tag(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating an item with a non-existent tag returns 404."""
    response = await client.post(
        "/items",
        json={
            "name": "Item",
            "tag_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_item_with_other_users_tag(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test creating an item with another user's tag returns 404."""
    other_tag = Tag(user_id=str(other_user.id), name="Other Tag")
    session.add(other_tag)
    await session.commit()
    await session.refresh(other_tag)

    response = await client.post(
        "/items",
        json={
            "name": "Item",
            "tag_ids": [other_tag.id],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_item_with_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating an item in a collection."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.post(
        "/items",
        json={
            "name": "Item in Collection",
            "collection_id": collection.id,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["collection_id"] == collection.id


@pytest.mark.asyncio
async def test_create_item_with_invalid_collection(
    client: AsyncClient, test_user: User, auth_client
):
    """Test creating an item with non-existent collection."""
    response = await client.post(
        "/items",
        json={
            "name": "Item",
            "collection_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_item_with_other_user_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test creating an item with another user's collection."""
    collection = Collection(user_id=str(other_user.id), name="Other's Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    response = await client.post(
        "/items",
        json={
            "name": "Item",
            "collection_id": collection.id,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_item_with_all_fields(client: AsyncClient, test_user: User, auth_client):
    """Test creating an item with all optional fields."""
    response = await client.post(
        "/items",
        json={
            "name": "Complete Item",
            "description": "Full description",
            "condition": "excellent",
            "location": "Living Room",
            "acquisition_date": "2024-01-15",
            "acquisition_price": "1500.00",
            "estimated_value": "2500.00",
            "artist_maker": "Unknown Artist",
            "origin": "France",
            "date_era": "19th Century",
            "provenance_notes": "Purchased at auction",
            "height_cm": "45.50",
            "width_cm": "30.00",
            "depth_cm": "15.00",
            "weight_kg": "5.500",
            "materials": "Oil on canvas, gilt frame",
            "notes": "Some restoration needed",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Complete Item"
    assert data["acquisition_price"] == "1500.00"
    assert data["height_cm"] == "45.50"


@pytest.mark.asyncio
async def test_list_items(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test listing items."""
    item1 = Item(user_id=str(test_user.id), name="Item 1")
    item2 = Item(user_id=str(test_user.id), name="Item 2")
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_items_filter_by_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test filtering items by collection."""
    collection = Collection(user_id=str(test_user.id), name="My Collection")
    session.add(collection)
    await session.commit()
    await session.refresh(collection)

    item1 = Item(user_id=str(test_user.id), name="In Collection", collection_id=collection.id)
    item2 = Item(user_id=str(test_user.id), name="Not in Collection")
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get(f"/items?collection_id={collection.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "In Collection"


@pytest.mark.asyncio
async def test_list_items_filter_by_tag(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test filtering items by tag name."""
    tag_art = Tag(user_id=str(test_user.id), name="Art")
    tag_furniture = Tag(user_id=str(test_user.id), name="Furniture")
    session.add_all([tag_art, tag_furniture])
    await session.commit()
    await session.refresh(tag_art)
    await session.refresh(tag_furniture)

    item1 = Item(user_id=str(test_user.id), name="Art Item")
    item1.tags = [tag_art]
    item2 = Item(user_id=str(test_user.id), name="Furniture Item")
    item2.tags = [tag_furniture]
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get("/items?tag=Art")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Art Item"


@pytest.mark.asyncio
async def test_list_items_search(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test searching items."""
    item1 = Item(user_id=str(test_user.id), name="Vintage Clock")
    item2 = Item(user_id=str(test_user.id), name="Modern Art", description="A vintage painting")
    item3 = Item(user_id=str(test_user.id), name="Table")
    session.add_all([item1, item2, item3])
    await session.commit()

    response = await client.get("/items?search=vintage")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [item["name"] for item in data]
    assert "Vintage Clock" in names
    assert "Modern Art" in names


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test getting a single item."""
    item = Item(user_id=str(test_user.id), name="My Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "My Item"


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient, test_user: User, auth_client):
    """Test getting a non-existent item."""
    response = await client.get("/items/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_item_other_user(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users cannot access other users' items."""
    item = Item(user_id=str(other_user.id), name="Other's Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_item(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating an item."""
    item = Item(user_id=str(test_user.id), name="Original Name")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}",
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_item_tags(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating an item's tags."""
    tag1 = Tag(user_id=str(test_user.id), name="Art")
    tag2 = Tag(user_id=str(test_user.id), name="Vintage")
    session.add_all([tag1, tag2])
    await session.commit()
    await session.refresh(tag1)
    await session.refresh(tag2)

    item = Item(user_id=str(test_user.id), name="Item")
    item.tags = [tag1]
    session.add(item)
    await session.commit()
    await session.refresh(item)

    # Update to different tags
    response = await client.patch(
        f"/items/{item.id}",
        json={"tag_ids": [tag2.id]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["tags"]) == 1
    assert data["tags"][0]["name"] == "Vintage"


@pytest.mark.asyncio
async def test_update_item_clear_tags(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test clearing an item's tags."""
    tag = Tag(user_id=str(test_user.id), name="Art")
    session.add(tag)
    await session.commit()
    await session.refresh(tag)

    item = Item(user_id=str(test_user.id), name="Item")
    item.tags = [tag]
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}",
        json={"tag_ids": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tags"] == []


@pytest.mark.asyncio
async def test_update_item_change_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test moving an item to a different collection."""
    collection1 = Collection(user_id=str(test_user.id), name="Collection 1")
    collection2 = Collection(user_id=str(test_user.id), name="Collection 2")
    session.add_all([collection1, collection2])
    await session.commit()
    await session.refresh(collection1)
    await session.refresh(collection2)

    item = Item(user_id=str(test_user.id), name="Item", collection_id=collection1.id)
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}",
        json={"collection_id": collection2.id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == collection2.id


@pytest.mark.asyncio
async def test_update_item_invalid_collection(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test updating item with another user's collection."""
    other_collection = Collection(user_id=str(other_user.id), name="Other's")
    session.add(other_collection)
    await session.commit()
    await session.refresh(other_collection)

    item = Item(user_id=str(test_user.id), name="My Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}",
        json={"collection_id": other_collection.id},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_item(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting an item."""
    item = Item(user_id=str(test_user.id), name="To Delete")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(f"/items/{item.id}")
    assert response.status_code == 204

    # Verify it's deleted
    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_items_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users only see their own items."""
    my_item = Item(user_id=str(test_user.id), name="My Item")
    other_item = Item(user_id=str(other_user.id), name="Other's Item")
    session.add_all([my_item, other_item])
    await session.commit()

    response = await client.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Item"
