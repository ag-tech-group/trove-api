import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User
from app.models.mark import Mark


@pytest.mark.asyncio
async def test_list_marks_empty(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test listing marks on an item with none."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.get(f"/items/{item.id}/marks")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a mark on an item."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(
        f"/items/{item.id}/marks",
        json={"title": "Stamp", "description": "Maker's stamp on base"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Stamp"
    assert data["description"] == "Maker's stamp on base"
    assert data["item_id"] == item.id


@pytest.mark.asyncio
async def test_create_mark_minimal(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a mark with no fields (both optional)."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.post(f"/items/{item.id}/marks", json={})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] is None
    assert data["description"] is None


@pytest.mark.asyncio
async def test_update_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a mark."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    mark = Mark(item_id=item.id, title="Old Title")
    session.add(mark)
    await session.commit()
    await session.refresh(mark)

    response = await client.patch(
        f"/items/{item.id}/marks/{mark.id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_update_mark_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test updating a non-existent mark returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.patch(
        f"/items/{item.id}/marks/00000000-0000-0000-0000-000000000000",
        json={"title": "X"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a mark."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    mark = Mark(item_id=item.id, title="To Delete")
    session.add(mark)
    await session.commit()
    await session.refresh(mark)

    response = await client.delete(f"/items/{item.id}/marks/{mark.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/marks")
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_mark_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test deleting a non-existent mark returns 404."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await client.delete(f"/items/{item.id}/marks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marks_user_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that marks on another user's item are inaccessible."""
    other_item = Item(user_id=str(other_user.id), name="Other Item")
    session.add(other_item)
    await session.commit()
    await session.refresh(other_item)

    response = await client.get(f"/items/{other_item.id}/marks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marks_cascade_delete(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test that marks are deleted when parent item is deleted."""
    item = Item(user_id=str(test_user.id), name="Item")
    session.add(item)
    await session.commit()
    await session.refresh(item)

    mark = Mark(item_id=item.id, title="Mark")
    session.add(mark)
    await session.commit()

    response = await client.delete(f"/items/{item.id}")
    assert response.status_code == 204

    response = await client.get(f"/items/{item.id}/marks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marks_on_nonexistent_item(client: AsyncClient, test_user: User, auth_client):
    """Test that marks on a nonexistent item return 404."""
    response = await client.get("/items/00000000-0000-0000-0000-000000000000/marks")
    assert response.status_code == 404
