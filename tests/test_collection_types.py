import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_collection_types(client: AsyncClient):
    """Test listing all collection types."""
    response = await client.get("/collection-types")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    names = [t["name"] for t in data]
    assert "general" in names
    assert "stamp" in names


@pytest.mark.asyncio
async def test_collection_types_structure(client: AsyncClient):
    """Test that collection types have the expected structure."""
    response = await client.get("/collection-types")
    data = response.json()
    for ct in data:
        assert "name" in ct
        assert "label" in ct
        assert "description" in ct
        assert "fields" in ct
        assert isinstance(ct["fields"], list)


@pytest.mark.asyncio
async def test_collection_types_stamp_fields(client: AsyncClient):
    """Test that stamp type has expected fields."""
    response = await client.get("/collection-types")
    data = response.json()
    stamp = next(t for t in data if t["name"] == "stamp")
    field_names = [f["name"] for f in stamp["fields"]]
    assert "denomination" in field_names
    assert "color" in field_names
    assert "catalogue_number" in field_names
    assert "mint_status" in field_names
    assert "perforation" in field_names
    assert "country_of_issue" in field_names


@pytest.mark.asyncio
async def test_collection_types_stamp_enum_field(client: AsyncClient):
    """Test that stamp mint_status field has enum options."""
    response = await client.get("/collection-types")
    data = response.json()
    stamp = next(t for t in data if t["name"] == "stamp")
    mint_status = next(f for f in stamp["fields"] if f["name"] == "mint_status")
    assert mint_status["type"] == "enum"
    assert "options" in mint_status
    option_values = [o["value"] for o in mint_status["options"]]
    assert "mint_never_hinged" in option_values
    assert "used" in option_values


@pytest.mark.asyncio
async def test_collection_types_general_no_fields(client: AsyncClient):
    """Test that general type has no fields."""
    response = await client.get("/collection-types")
    data = response.json()
    general = next(t for t in data if t["name"] == "general")
    assert general["fields"] == []
