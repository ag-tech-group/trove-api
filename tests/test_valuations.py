import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, User, Valuation


async def _item(session: AsyncSession, user: User, name: str = "Item") -> Item:
    item = Item(user_id=str(user.id), name=name)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def _valuation(session: AsyncSession, item: Item, value: str = "100.00") -> Valuation:
    valuation = Valuation(item_id=item.id, value=value)
    session.add(valuation)
    await session.commit()
    await session.refresh(valuation)
    return valuation


async def test_list_valuations_empty(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)

    response = await client.get(f"/items/{item.id}/valuations")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_valuation(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)

    response = await client.post(
        f"/items/{item.id}/valuations",
        json={
            "value": "1250.00",
            "valued_on": "2021-03",
            "appraiser": "Regional auction house",
            "valuation_type": "Insurance appraisal",
            "notes": "Replacement value",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["item_id"] == item.id
    assert data["value"] == "1250.00"
    assert data["valued_on"] == "2021-03"
    assert data["appraiser"] == "Regional auction house"
    assert data["valuation_type"] == "Insurance appraisal"
    assert data["notes"] == "Replacement value"


@pytest.mark.parametrize(
    "body",
    [{}, {"value": "-1.00"}, {"value": "10.00", "valued_on": "2021-13"}],
    ids=["missing value", "negative value", "impossible month"],
)
async def test_create_valuation_rejects_invalid_input(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client, body
):
    item = await _item(session, test_user)

    response = await client.post(f"/items/{item.id}/valuations", json=body)

    assert response.status_code == 422


async def test_update_valuation(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)
    valuation = await _valuation(session, item)

    response = await client.patch(
        f"/items/{item.id}/valuations/{valuation.id}",
        json={"value": "150.00", "valued_on": "2024"},
    )

    assert response.status_code == 200
    assert response.json()["value"] == "150.00"
    assert response.json()["valued_on"] == "2024"


async def test_update_valuation_cannot_clear_the_value(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)
    valuation = await _valuation(session, item)

    response = await client.patch(
        f"/items/{item.id}/valuations/{valuation.id}", json={"value": None}
    )

    assert response.status_code == 422


async def test_update_valuation_not_found(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)

    response = await client.patch(
        f"/items/{item.id}/valuations/00000000-0000-0000-0000-000000000000",
        json={"value": "1.00"},
    )

    assert response.status_code == 404


async def test_delete_valuation(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)
    valuation = await _valuation(session, item)

    response = await client.delete(f"/items/{item.id}/valuations/{valuation.id}")

    assert response.status_code == 204
    assert (await client.get(f"/items/{item.id}/valuations")).json() == []


async def test_valuations_user_isolation(
    client: AsyncClient, session: AsyncSession, other_user: User, auth_client
):
    other_item = await _item(session, other_user, "Other Item")
    valuation = await _valuation(session, other_item)

    assert (await client.get(f"/items/{other_item.id}/valuations")).status_code == 404
    response = await client.patch(
        f"/items/{other_item.id}/valuations/{valuation.id}", json={"value": "1.00"}
    )
    assert response.status_code == 404


async def test_valuations_in_item_response(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)
    await _valuation(session, item, "75.50")

    response = await client.get(f"/items/{item.id}")

    assert [v["value"] for v in response.json()["valuations"]] == ["75.50"]


async def test_valuations_are_deleted_with_their_item(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_client
):
    item = await _item(session, test_user)
    await _valuation(session, item)

    response = await client.delete(f"/items/{item.id}")

    assert response.status_code == 204
    remaining = await session.execute(select(Valuation).where(Valuation.item_id == item.id))
    assert remaining.scalars().all() == []
