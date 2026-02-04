"""Collection type registry.

Defines available collection types and their type-specific field schemas.
"""

COLLECTION_TYPES: dict = {
    "general": {
        "label": "General",
        "description": "General collection with no type-specific fields",
        "fields": [],
    },
    "stamp": {
        "label": "Stamps",
        "description": "Postage stamp collection",
        "fields": [
            {
                "name": "denomination",
                "label": "Denomination",
                "type": "string",
                "max_length": 100,
            },
            {
                "name": "color",
                "label": "Color",
                "type": "string",
                "max_length": 100,
            },
            {
                "name": "catalogue_number",
                "label": "Catalogue Number",
                "type": "string",
                "max_length": 100,
            },
            {
                "name": "mint_status",
                "label": "Mint Status",
                "type": "enum",
                "options": [
                    {"value": "mint_never_hinged", "label": "Mint Never Hinged (MNH)"},
                    {"value": "mint_hinged", "label": "Mint Hinged (MH)"},
                    {"value": "mint_og", "label": "Mint Original Gum (OG)"},
                    {"value": "used", "label": "Used"},
                    {"value": "on_cover", "label": "On Cover"},
                    {"value": "on_piece", "label": "On Piece"},
                ],
            },
            {
                "name": "perforation",
                "label": "Perforation",
                "type": "string",
                "max_length": 100,
            },
            {
                "name": "watermark",
                "label": "Watermark",
                "type": "string",
                "max_length": 200,
            },
            {
                "name": "variety",
                "label": "Variety",
                "type": "string",
                "max_length": 200,
            },
            {
                "name": "series",
                "label": "Series",
                "type": "string",
                "max_length": 200,
            },
            {
                "name": "issue_date",
                "label": "Issue Date",
                "type": "string",
                "max_length": 100,
            },
            {
                "name": "country_of_issue",
                "label": "Country of Issue",
                "type": "string",
                "max_length": 200,
            },
        ],
    },
}


def get_type_field_names(collection_type: str) -> set[str]:
    """Return the set of valid field names for a collection type."""
    type_def = COLLECTION_TYPES.get(collection_type)
    if not type_def:
        return set()
    return {f["name"] for f in type_def["fields"]}


def validate_type_fields(collection_type: str, type_fields: dict) -> dict:
    """Strip unknown fields and return only valid ones."""
    valid = get_type_field_names(collection_type)
    return {k: v for k, v in type_fields.items() if k in valid}


def get_all_types() -> list[dict]:
    """Return the type registry as a list for API responses."""
    return [{"name": name, **definition} for name, definition in COLLECTION_TYPES.items()]
