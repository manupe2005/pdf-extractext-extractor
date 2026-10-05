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
| `MAX_UPLOAD_BYTES` | `67108864`              | Límite defensivo del cuerpo de la petición (bytes) |
| `MAX_CONCURRENCY` | `1`                      | Extracciones simultáneas admitidas **por proceso/worker**; el exceso recibe 503 inmediato |
| `RETRY_AFTER_SECONDS` | `1`                 | Valor del header `Retry-After` en los rechazos 503 |

Gunicorn (servidor): `WEB_CONCURRENCY` (workers, default `4`) y
`GUNICORN_BACKLOG` (backlog de socket acotado, default `64`) en
`gunicorn.conf.py`. La admisión total por contenedor es
`WEB_CONCURRENCY × MAX_CONCURRENCY` (4 × 1 = 4 con los defaults,
dimensionado para 1 CPU / 1 GB; ajustable tras mediciones).

## API

### `POST /extract`

Recibe un PDF por `multipart/form-data` (campo `file`) y lo procesa 100% en
memoria, sin tocar el disco. Fase actual: recepción.

- `200` -> `{"filename": "<original>", "size": <bytes>}` (la extracción de
  texto y el checksum se agregan en issues posteriores sobre esta misma ruta).
- `400` -> `{"code": "INVALID_REQUEST", "message": "<detalle>"}` cuando falla
  la validación estructural: falta el campo `file`, el archivo está vacío, el
  multipart está corrupto o el cuerpo supera el límite defensivo.
- `503` -> `{"code": "INTERNAL_ERROR", "message": "<detalle>"}` con header
  `Retry-After` cuando el control de admisión está saturado (backpressure,
  rechazo inmediato sin acumulación).

```bash
curl -F "file=@documento.pdf" http://localhost:8000/extract
```

## Desarrollo

```bash
# Instalar dependencias
uv sync

# Ejecutar la aplicación (desarrollo)
uv run uvicorn pdf_extractext_extractor.main:app --app-dir src --reload

# Ejecutar como en producción (Gunicorn + workers Uvicorn)
uv run gunicorn pdf_extractext_extractor.main:app -c gunicorn.conf.py

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
│       ├── errors.py                 # Contrato de error 400 INVALID_REQUEST
│       ├── extraction.py             # POST /extract (recepción multipart)
│       └── main.py                   # App FastAPI + GET /health
└── tests/
    ├── conftest.py                   # Fixture multipart válida (compartible)
    ├── test_health.py                # /health + guardas de arquitectura
    └── test_extraction.py            # POST /extract
```
