# trove-api

All commands use `uv run` — never call python/pytest/alembic directly. See `pyproject.toml` for available scripts.

## Verification

After making changes, always verify before committing:

1. `uv run ruff check` + `uv run ruff format` — lint and format
2. `uv run pytest` — run tests (prefer single test files when iterating)
3. If adding a feature or fixing a bug, write or update tests and confirm they pass.

Pre-commit runs both Ruff (lint + format) AND the full test suite. Commits are blocked if any test fails.

## Key Conventions

- **String UUIDs:** All IDs are stored as strings, not Python UUID objects. Use `str(uuid4())` for defaults, `str(user.id)` in queries.
- **Ownership filtering:** Every query for user-owned data MUST include `Model.user_id == str(user.id)` in the WHERE clause. Never return data without this check.
- **Type registry:** Collection types and their allowed fields are defined in `app/type_registry.py` (not in the database). Use `validate_type_fields()` to whitelist-filter incoming type_fields.

## Alembic Gotcha

When adding a new model, you MUST import it in `alembic/env.py` alongside the existing model imports — otherwise `--autogenerate` won't detect it.

## Testing

- Tests use **SQLite in-memory** (`sqlite+aiosqlite`), not PostgreSQL.
- `conftest.py` provides `auth_client` (authenticated), `client` (anonymous), `test_user`, `other_user`, and a `session` fixture.
- Pytest runs in `asyncio_mode = "auto"` — async test functions just work.

## Code Style

- Ruff with 100-char line length.
- B008 is ignored (allows `Depends()` in function signatures).
