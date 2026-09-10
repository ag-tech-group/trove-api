FROM python:3.14-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code and migrations
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Sentry release identity, baked in at build time so the running code and the
# release it reports come from the same artifact. CI passes the commit SHA with
# --build-arg. Declared last so a new SHA never busts the `uv sync` layer above:
# under BuildKit every layer after an invalidated ARG rebuilds.
#
# THE DEFAULT MUST STAY EMPTY, not a placeholder like "unknown". app/sentry.py
# passes `settings.sentry_release or None`, and on None the SDK runs its own
# detection, which outside a git repo picks up Cloud Run's K_REVISION — so an
# empty default degrades to a real identifier:
#
#   SENTRY_RELEASE=''         K_REVISION=trove-api-00042-abc -> trove-api-00042-abc
#   SENTRY_RELEASE='unknown'  K_REVISION=trove-api-00042-abc -> unknown
#
# A placeholder suppresses that fallback and mints a release literally named
# "unknown" that every hand-built image collapses into, breaking "first seen in
# release" and regression detection.
#
# Cloud Run precedence: a variable set on the SERVICE beats one baked into the
# image. Infrastructure owns this service's env, so adding SENTRY_RELEASE there
# would silently shadow this and pin Sentry to a stale release. Set it here or
# not at all.
ARG GIT_SHA=
ENV SENTRY_RELEASE=$GIT_SHA

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
