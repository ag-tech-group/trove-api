import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User
from app.models.item_note import ItemNote


@pytest.mark.asyncio
async def test_list_item_notes_empty(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing notes on an item with none."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}/notes")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_item_note(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a note on an item."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/notes",
        json={"title": "Condition Report", "body": "Minor scratches on base"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Condition Report"
    assert data["body"] == "Minor scratches on base"
    assert data["item_id"] == item.id


@pytest.mark.asyncio
async def test_create_item_note_missing_body(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a note without body returns 422."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/notes",
        json={"title": "No Body"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_item_note_minimal(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a note with only body (title is optional)."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/notes",
        json={"body": "Just a note"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] is None
    assert data["body"] == "Just a note"


@pytest.mark.asyncio
async def test_update_item_note(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a note."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    note = ItemNote(item_id=item.id, body="Original body")
    session.add(note)
    await session.commit()
    await session.refresh(note)

    response = await client.patch(
        f"/items/{item.id}/notes/{note.id}",
        json={"body": "Updated body", "title": "Added Title"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["body"] == "Updated body"
    assert data["title"] == "Added Title"


@pytest.mark.asyncio
async def test_update_item_note_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a non-existent note returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}/notes/00000000-0000-0000-0000-000000000000",
        json={"body": "X"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_item_note(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a note."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    note = ItemNote(item_id=item.id, body="To Delete")
    session.add(note)
    await session.commit()
    await session.refresh(note)

    response = await client.delete(f"/items/{item.id}/notes/{note.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/notes")
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_item_note_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a non-existent note returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(f"/items/{item.id}/notes/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_item_notes_user_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that notes on another user's item are inaccessible."""
    other_item = Item(user_id=str(other_user.id), name="Other Item")
    session.add(other_item)
    await session.commit()
    await session.refresh(other_item)

    response = await client.get(f"/items/{other_item.id}/notes")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_item_notes_cascade_delete(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that notes are deleted when parent item is deleted."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    note = ItemNote(item_id=item.id, body="Note")
    session.add(note)
    await session.commit()

    response = await client.delete(f"/items/{item.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/notes")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_item_notes_on_nonexistent_item(client: AsyncClient, test_user: User, auth_client):
    """Test that notes on a nonexistent item return 404."""
    response = await client.get("/items/00000000-0000-0000-0000-000000000000/notes")
    assert response.status_code == 404
