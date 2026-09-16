# pdf-extractext-extraction

Microservicio de extracción de texto de PDFs. **Estado actual:** bootstrap inicial — solo incluye la base del servicio y un endpoint de health check.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 y las dependencias)
- Opcional: Docker

## Configuración

La configuración se define mediante variables de entorno (ver `src/pdf_extractext_extractor/config.py`):

| Variable      | Default                     | Descripción          |
| ------------- | --------------------------- | -------------------- |
| `APP_NAME`    | `pdf-extractext-extractor`  | Nombre del servicio  |
| `APP_VERSION` | `0.1.0`                     | Versión              |
| `PORT`        | `8000`                      | Puerto de escucha    |

## Desarrollo

```bash
# Instalar dependencias
uv sync

# Ejecutar la aplicación
uv run uvicorn pdf_extractext_extractor.main:app --app-dir src --reload

# Health check
curl http://localhost:8000/health
```

## Tests

```bash
uv run pytest
```

## Docker

```bash
docker build -t pdf-extractext-extraction .
docker run -p 8000:8000 pdf-extractext-extraction
```

## Estructura

```
├── pyproject.toml                    # Dependencias y metadatos (uv)
├── Dockerfile
├── .dockerignore
├── .gitignore
├── src/
│   └── pdf_extractext_extractor/
│       ├── __init__.py
│       ├── config.py                 # Settings por variables de entorno
│       └── main.py                   # App FastAPI + GET /health
└── tests/
    └── test_health.py                # Test unitario de /health
```
