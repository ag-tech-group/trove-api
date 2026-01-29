import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, Item, User


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
