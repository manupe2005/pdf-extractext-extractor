# pdf-extractext-extraction

Microservicio de extracción de texto de PDFs. Recibe un PDF por HTTP, extrae su
texto con PyMuPDF y lo devuelve convertido a **Markdown estructurado**, todo
100% en memoria (cero escrituras a disco en el hot path).

**Estado actual:** funcional — extracción + checksum SHA-256, control de
admisión con backpressure y probes de liveness/readiness. Los documentos de
`tasks/` corresponden al plan de bootstrap original (histórico).

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

### Endpoints

- `GET /health` -> liveness: `{"status": "ok", "service": "<app_name>", "version": "<app_version>"}`.
- `GET /readyz` -> readiness: `{"status": "ok"}`.
- `POST /extract` -> extracción (ver abajo).

### `POST /extract`

Recibe un PDF por `multipart/form-data` (campo `file`) y lo procesa 100% en
memoria, sin tocar el disco. Extrae el texto con PyMuPDF y lo devuelve
convertido a **Markdown estructurado** (encabezados `#`–`###`, listas y
separadores de página `---`).

- `200` -> contrato C1 + TP (5 campos):

```json
{
  "filename": "<original>",
  "extracted_text": "<Markdown>",
  "checksum": "<SHA-256 hex>",
  "content": "<Markdown>",
  "page_count": 42
}
```

  Regla estricta: `extracted_text == content` (mismo string). Un PDF sin texto
  devuelve `""`.

Los errores responden `Content-Type: application/problem+json` (RFC 9457) con
los campos `type` (URN), `title`, `status`, `detail` + el miembro de extensión
`code`:

| Status | `code` | Cuándo |
|---|---|---|
| `400` | `INVALID_REQUEST` | Validación estructural: falta el campo `file`, archivo vacío, multipart corrupto o cuerpo que supera `MAX_UPLOAD_BYTES`. |
| `422` | `INVALID_PDF_CONTENT` | El contenido no es un PDF válido/procesable. |
| `500` | `INTERNAL_ERROR` | Fallo interno de procesamiento. |
| `503` | `SERVICE_OVERLOADED` | Control de admisión saturado (backpressure, rechazo inmediato) — siempre con header `Retry-After`. |

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

Imagen multi-stage: lockfile congelado (`uv sync --locked --no-dev
--no-editable`), runtime sin dev-deps, usuario no-root y healthcheck de
liveness. El `docker-compose.yml` de este repo es **solo para
smoke/desarrollo local**: aplica límites explícitos (1 CPU / 1 GB) y no
publica puertos (red interna). La integración del sistema completo vive
en `pdf-extractext-infrastructure`.

```bash
# Smoke contra el contenedor (build + up + liveness + stats + down)
make smoke

# Solo build/run manuales
docker build -t pdf-extractext-extractor:local .
docker compose up -d --wait
```

## Estructura

```
├── pyproject.toml                    # Dependencias y metadatos (uv)
├── Dockerfile                        # Multi-stage, no-root, healthcheck
├── docker-compose.yml                # Smoke local: límites 1 CPU / 1 GB, sin ports
├── gunicorn.conf.py                  # Workers por env, backlog acotado
├── Makefile                          # test / smoke / load-test / stress-test / perf-sustained
├── src/
│   └── pdf_extractext_extractor/
│       ├── config.py                 # Settings por variables de entorno
│       ├── admission.py              # Control de admisión 503 + Retry-After
│       ├── checksum.py               # SHA-256 del PDF
│       ├── errors.py                 # Errores RFC 9457 (400 / 422 / 500 / 503)
│       ├── extraction.py             # POST /extract (multipart + dominio)
│       ├── main.py                   # App FastAPI + GET /health + GET /readyz
│       └── domain/
│           ├── extractor.py          # PDF -> Markdown con PyMuPDF
│           └── exceptions.py         # Errores de dominio (422 / 500)
├── docs/
│   ├── adr/                          # Decisiones de arquitectura
│   └── performance-issue-9.md        # Mediciones de CPU/RAM bajo carga
└── tests/                            # unitarios (api/, domain/), integration/, load/
```
