import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, Item, User


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
            "category": "Clock/Watch",
            "condition": "good",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Vintage Clock"
    assert data["description"] == "A beautiful antique clock"
    assert data["category"] == "Clock/Watch"
    assert data["condition"] == "good"
    assert data["user_id"] == str(test_user.id)


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
            "category": "Art",
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
async def test_list_items_filter_by_category(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test filtering items by category."""
    item1 = Item(user_id=str(test_user.id), name="Art Item", category="Art")
    item2 = Item(user_id=str(test_user.id), name="Furniture Item", category="Furniture")
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get("/items?category=Art")
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
    item = Item(user_id=str(test_user.id), name="My Item", category="Art")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "My Item"
    assert data["category"] == "Art"


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
        json={"name": "Updated Name", "category": "Art"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["category"] == "Art"


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


@pytest.mark.asyncio
async def test_list_categories(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing categories returns suggested plus custom."""
    # Create items with custom categories
    item1 = Item(user_id=str(test_user.id), name="Item 1", category="Art")  # Suggested
    item2 = Item(user_id=str(test_user.id), name="Item 2", category="Custom Category")  # Custom
    session.add_all([item1, item2])
    await session.commit()

    response = await client.get("/categories")
    assert response.status_code == 200
    data = response.json()
    assert "Art" in data  # Suggested category
    assert "Custom Category" in data  # Custom category
    assert "Antique" in data  # Another suggested category (even though no items)
