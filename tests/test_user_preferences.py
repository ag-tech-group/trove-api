import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def test_units_default_to_metric(client: AsyncClient, test_user: User, auth_client):
    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["preferred_units"] == "metric"


async def test_patch_me_sets_preferred_units(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    response = await client.patch("/auth/me", json={"preferred_units": "imperial"})

    assert response.status_code == 200
    assert response.json()["preferred_units"] == "imperial"
    await session.refresh(test_user)
    assert test_user.preferred_units == "imperial"


@pytest.mark.parametrize("body", [{"preferred_units": "furlongs"}, {"preferred_units": None}])
async def test_patch_me_rejects_invalid_units(
    client: AsyncClient, test_user: User, auth_client, body
):
    response = await client.patch("/auth/me", json=body)

    assert response.status_code == 422


async def test_patch_me_leaves_credentials_alone(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    """PATCH /auth/me changes settings only; the fields that grant access are not in its schema."""
    response = await client.patch(
        "/auth/me",
        json={"email": "new@example.com", "is_superuser": True, "password": "x"},
    )

    assert response.status_code == 200
    await session.refresh(test_user)
    assert test_user.email == "test@example.com"
    assert test_user.is_superuser is False
    assert test_user.hashed_password == "fakehash"


async def test_patch_me_requires_authentication(client: AsyncClient):
    response = await client.patch("/auth/me", json={"preferred_units": "imperial"})

    assert response.status_code == 401
