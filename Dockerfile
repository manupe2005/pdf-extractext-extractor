# syntax=docker/dockerfile:1
# Multi-stage: lockfile congelado, runtime no-root sin dev-deps.

# ---- Stage 1: build ----
FROM python:3.12-slim AS build

# uv fijado por versión para builds reproducibles.
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /bin/

WORKDIR /app

# Precompilar .pyc y usar cache de uv para acelerar arranque/rebuilds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Capas de dependencias primero para aprovechar el cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
# Wheel real en site-packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- Stage 2: runtime ----
FROM python:3.12-slim

# Aplicar parches disponibles de Debian (Trivy: avisos OS tipo util-linux,
# zlib1g pendientes de parche oficial se reducen al mínimo en build).
# Debe correr como root, antes de crear el usuario no-root.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

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
