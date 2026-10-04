FROM python:3.12-slim

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Instalar dependencias primero
COPY pyproject.toml uv.lock* ./
RUN uv sync --locked --no-dev --no-install-project

# Copiar el código fuente
COPY src ./src

# Instalar el proyecto
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8001

CMD ["uvicorn", "pdf_extractext_extractor.main:app", "--host", "0.0.0.0", "--port", "8001"]
