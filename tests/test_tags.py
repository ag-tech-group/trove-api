import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tag, User


@pytest.mark.asyncio
async def test_create_tag(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test creating a tag."""
    response = await client.post("/tags", json={"name": "Art"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Art"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_tag_duplicate(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test creating a duplicate tag returns 409."""
    tag = Tag(user_id=str(test_user.id), name="Art")
    session.add(tag)
    await session.commit()

    response = await client.post("/tags", json={"name": "Art"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_tags(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test listing tags returns alphabetical order."""
    tag1 = Tag(user_id=str(test_user.id), name="Zebra")
    tag2 = Tag(user_id=str(test_user.id), name="Art")
    tag3 = Tag(user_id=str(test_user.id), name="Music")
    session.add_all([tag1, tag2, tag3])
    await session.commit()

    response = await client.get("/tags")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["name"] == "Art"
    assert data[1]["name"] == "Music"
    assert data[2]["name"] == "Zebra"


@pytest.mark.asyncio
async def test_update_tag(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test renaming a tag."""
    tag = Tag(user_id=str(test_user.id), name="Art")
    session.add(tag)
    await session.commit()
    await session.refresh(tag)

    response = await client.patch(f"/tags/{tag.id}", json={"name": "Fine Art"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Fine Art"


@pytest.mark.asyncio
async def test_update_tag_duplicate_name(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """Test renaming a tag to an existing name returns 409."""
    tag1 = Tag(user_id=str(test_user.id), name="Art")
    tag2 = Tag(user_id=str(test_user.id), name="Music")
    session.add_all([tag1, tag2])
    await session.commit()
    await session.refresh(tag1)

    response = await client.patch(f"/tags/{tag1.id}", json={"name": "Music"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_tag_not_found(client: AsyncClient, test_user: User, auth_client):
    """Test updating a non-existent tag returns 404."""
    response = await client.patch(
        "/tags/00000000-0000-0000-0000-000000000000", json={"name": "Art"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_tag(client: AsyncClient, session: AsyncSession, test_user: User, auth_client):
    """Test deleting a tag."""
    tag = Tag(user_id=str(test_user.id), name="Art")
    session.add(tag)
    await session.commit()
    await session.refresh(tag)

    response = await client.delete(f"/tags/{tag.id}")
    assert response.status_code == 204

    # Verify it's deleted
    response = await client.get("/tags")
    data = response.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_delete_tag_not_found(client: AsyncClient, test_user: User, auth_client):
    """Test deleting a non-existent tag returns 404."""
    response = await client.delete("/tags/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tags_isolation(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users only see their own tags."""
    my_tag = Tag(user_id=str(test_user.id), name="My Tag")
    other_tag = Tag(user_id=str(other_user.id), name="Other Tag")
    session.add_all([my_tag, other_tag])
    await session.commit()

    response = await client.get("/tags")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Tag"


@pytest.mark.asyncio
async def test_cannot_update_other_users_tag(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users cannot rename another user's tag."""
    other_tag = Tag(user_id=str(other_user.id), name="Other Tag")
    session.add(other_tag)
    await session.commit()
    await session.refresh(other_tag)

    response = await client.patch(f"/tags/{other_tag.id}", json={"name": "Stolen"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_other_users_tag(
    client: AsyncClient, session: AsyncSession, test_user: User, other_user: User, auth_client
):
    """Test that users cannot delete another user's tag."""
    other_tag = Tag(user_id=str(other_user.id), name="Other Tag")
    session.add(other_tag)
    await session.commit()
    await session.refresh(other_tag)

    response = await client.delete(f"/tags/{other_tag.id}")
    assert response.status_code == 404
