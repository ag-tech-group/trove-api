<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark.png">
  <source media="(prefers-color-scheme: light)" srcset=".github/assets/logo-light.png">
  <img alt="AG Technology Group" src=".github/assets/logo-light.png" width="200">
</picture>

# Trove API

[![CI](https://github.com/ag-tech-group/trove-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ag-tech-group/trove-api/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](https://www.python.org/)

Personal collection management API for tracking antiques, art, and valuables.

## Tech Stack

| Component          | Technology                     |
| ------------------ | ------------------------------ |
| Framework          | FastAPI                        |
| Database           | PostgreSQL (async via asyncpg) |
| ORM                | SQLAlchemy 2.0                 |
| Migrations         | Alembic                        |
| Auth               | FastAPI-Users (JWT)            |
| Package Manager    | uv                             |
| Containerization   | Docker / Docker Compose        |
| Testing            | Pytest (async)                 |
| Linting/Formatting | Ruff                           |

## Requirements

- Python 3.12+
- uv
- Docker & Docker Compose (for local development)

## Quick Start

```bash
# Clone and enter directory
cd trove-api

# Copy environment file
cp .env.example .env

# Install dependencies
uv sync

# Start PostgreSQL
docker compose up -d db

# Run migrations
uv run alembic upgrade head

# Start the API
uv run uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

## Running with Docker

```bash
# Start everything (API + PostgreSQL)
docker compose up

# Or run in background
docker compose up -d
```

## API Documentation

Once running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## API Endpoints

### Auth

| Method | Endpoint          | Description          |
| ------ | ----------------- | -------------------- |
| POST   | `/auth/register`  | Create a new account |
| POST   | `/auth/jwt/login` | Get JWT access token |

### Collections

| Method | Endpoint             | Auth | Description                   |
| ------ | -------------------- | ---- | ----------------------------- |
| GET    | `/collections`       | Yes  | List user's collections       |
| GET    | `/collections/{id}`  | Yes  | Get collection with item count|
| POST   | `/collections`       | Yes  | Create a collection           |
| PATCH  | `/collections/{id}`  | Yes  | Update a collection           |
| DELETE | `/collections/{id}`  | Yes  | Delete a collection           |

### Items

| Method | Endpoint       | Auth | Description                      |
| ------ | -------------- | ---- | -------------------------------- |
| GET    | `/items`       | Yes  | List items (supports filters)    |
| GET    | `/items/{id}`  | Yes  | Get an item by ID                |
| POST   | `/items`       | Yes  | Create an item                   |
| PATCH  | `/items/{id}`  | Yes  | Update an item                   |
| DELETE | `/items/{id}`  | Yes  | Delete an item                   |

**Item List Filters:**
- `collection_id` - Filter by collection
- `category` - Filter by category
- `search` - Search in name and description

### Categories

| Method | Endpoint      | Auth | Description                           |
| ------ | ------------- | ---- | ------------------------------------- |
| GET    | `/categories` | Yes  | List suggested + user's categories    |

## Data Model

### Collection
- `id` - UUID
- `name` - String (max 200)
- `description` - Text (optional)
- `created_at`, `updated_at` - Timestamps

### Item
- **Basic Info:** name, description, category, condition, location
- **Financials:** acquisition_date, acquisition_price, estimated_value
- **Provenance:** artist_maker, origin, date_era, provenance_notes
- **Physical:** height_cm, width_cm, depth_cm, weight_kg, materials
- **Metadata:** notes, created_at, updated_at

**Condition Options:** excellent, good, fair, poor, unknown

## Database Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Generate new migration after model changes
uv run alembic revision --autogenerate -m "description"
```

## Testing

Tests use SQLite in-memory for speed and isolation.

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=app
```

## Linting & Formatting

```bash
# Check for linting errors
uv run ruff check .

# Format code
uv run ruff format .
```

## Project Structure

```
trove-api/
├── app/
│   ├── auth/           # FastAPI-Users JWT setup
│   ├── models/         # SQLAlchemy models (User, Collection, Item)
│   ├── routers/        # API route handlers
│   ├── schemas/        # Pydantic request/response schemas
│   ├── config.py       # Settings from environment
│   ├── database.py     # Async SQLAlchemy setup
│   └── main.py         # FastAPI app entry point
├── alembic/
│   ├── versions/       # Migration files
│   └── env.py          # Alembic configuration
├── tests/
│   ├── conftest.py     # Pytest fixtures
│   ├── test_collections.py
│   └── test_items.py
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Environment Variables

| Variable       | Description                   | Default                                                          |
| -------------- | ----------------------------- | ---------------------------------------------------------------- |
| `DATABASE_URL` | PostgreSQL connection string  | `postgresql+asyncpg://postgres:postgres@localhost:5432/trove_db` |
| `SECRET_KEY`   | JWT signing key               | `change-me-in-production`                                        |
| `ENVIRONMENT`  | `development` or `production` | `development`                                                    |

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
