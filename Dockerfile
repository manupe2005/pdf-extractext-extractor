# syntax=docker/dockerfile:1
# Multi-stage: lockfile congelado, runtime no-root sin dev-deps (Issue #7).

# ---- Stage 1: build ----
FROM python:3.12-slim AS build

# uv fijado por versión para builds reproducibles.
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /bin/

WORKDIR /app

# Capas de dependencias primero para aprovechar el cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
# Wheel real en site-packages: un editable apuntaría a /app/src, ausente en runtime.
RUN uv sync --locked --no-dev --no-editable

# ---- Stage 2: runtime ----
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY gunicorn.conf.py ./

ENV PATH="/app/.venv/bin:$PATH"

USER appuser
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')"]

CMD ["gunicorn", "pdf_extractext_extractor.main:app", "-c", "gunicorn.conf.py"]
