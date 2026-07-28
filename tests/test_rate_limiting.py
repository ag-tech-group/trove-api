"""Global rate limiting behaviour.

Every route outside the exempt infrastructure set gets the in-house
300/min default (auth endpoints keep their stricter per-path limits).
The default is enforced by our own middleware calling `limits` directly,
so it is immune to the FastAPI >=0.137 / slowapi issue #281 regression
that breaks SlowAPIMiddleware-based default_limits.
"""

from httpx import AsyncClient


class TestGlobalRateLimit:
    async def test_default_limit_applies_to_non_auth_routes(self, client: AsyncClient):
        # /collections is an ordinary API route with no per-path limit, so
        # it gets the 300/min default (matches _DEFAULT_RATE_LIMIT in
        # app/main.py — bump both together if that changes). The limit is
        # consumed regardless of auth outcome, so unauthenticated traffic
        # cannot hammer the route either.
        for _ in range(300):
            assert (await client.get("/collections")).status_code != 429
        assert (await client.get("/collections")).status_code == 429

    async def test_infrastructure_routes_are_exempt(self, client: AsyncClient):
        # / and /health must never 429 — probes and uptime checks hit them
        # far more often than any human client.
        for _ in range(310):
            assert (await client.get("/health")).status_code == 200
        assert (await client.get("/")).status_code == 200
