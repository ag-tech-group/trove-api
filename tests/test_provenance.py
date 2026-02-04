import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User
from app.models.provenance_entry import ProvenanceEntry


@pytest.mark.asyncio
async def test_list_provenance_empty(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing provenance entries on an item with none."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}/provenance")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_provenance_entry(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a provenance entry."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/provenance",
        json={
            "owner_name": "John Smith",
            "date_from": "circa 1850",
            "date_to": "1920s",
            "notes": "Inherited from estate",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["owner_name"] == "John Smith"
    assert data["date_from"] == "circa 1850"
    assert data["date_to"] == "1920s"
    assert data["notes"] == "Inherited from estate"
    assert data["item_id"] == item.id


@pytest.mark.asyncio
async def test_create_provenance_entry_missing_owner_name(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a provenance entry without owner_name returns 422."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/provenance",
        json={"date_from": "1900"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_provenance_entry(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a provenance entry."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    entry = ProvenanceEntry(item_id=item.id, owner_name="Original Owner")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    response = await client.patch(
        f"/items/{item.id}/provenance/{entry.id}",
        json={"owner_name": "Updated Owner", "date_from": "1900"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["owner_name"] == "Updated Owner"
    assert data["date_from"] == "1900"


@pytest.mark.asyncio
async def test_update_provenance_entry_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a non-existent provenance entry returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}/provenance/00000000-0000-0000-0000-000000000000",
        json={"owner_name": "X"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_provenance_entry(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a provenance entry."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    entry = ProvenanceEntry(item_id=item.id, owner_name="To Delete")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    response = await client.delete(f"/items/{item.id}/provenance/{entry.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/provenance")
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_provenance_entry_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a non-existent provenance entry returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(
        f"/items/{item.id}/provenance/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provenance_user_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that provenance on another user's item is inaccessible."""
    other_item = Item(user_id=str(other_user.id), name="Other Item")
    session.add(other_item)
    await session.commit()
    await session.refresh(other_item)

    response = await client.get(f"/items/{other_item.id}/provenance")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provenance_cascade_delete(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that provenance entries are deleted when parent item is deleted."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    entry = ProvenanceEntry(item_id=item.id, owner_name="Owner")
    session.add(entry)
    await session.commit()

    response = await client.delete(f"/items/{item.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/provenance")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provenance_on_nonexistent_item(client: AsyncClient, test_user: User, auth_client):
    """Test that provenance on a nonexistent item returns 404."""
    response = await client.get("/items/00000000-0000-0000-0000-000000000000/provenance")
    assert response.status_code == 404
