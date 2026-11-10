# pdf-extractext-extraction

Microservicio de extracción de texto de PDFs. Recibe un PDF por HTTP, extrae su
texto con PyMuPDF y lo devuelve convertido a **Markdown estructurado**, todo
100% en memoria (cero escrituras a disco en el hot path).

**Estado actual:** funcional — extracción + checksum SHA-256, control de
admisión con backpressure, probes de liveness/readiness e integración con
Consul (registro, health y configuración KV) para Traefik. Los documentos de
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
| `GIT_COMMIT`  | `unknown`                   | Commit publicado en `Meta` de Consul |
| `PORT`        | `8001`                      | Puerto de escucha (bind de Gunicorn) |
| `MAX_UPLOAD_BYTES` | `67108864`              | Límite defensivo del cuerpo de la petición (bytes) |
| `MAX_CONCURRENCY` | `1`                      | Extracciones simultáneas admitidas **por proceso/worker**; el exceso recibe 503 inmediato |
| `RETRY_AFTER_SECONDS` | `1`                 | Valor del header `Retry-After` en los rechazos 503 |
| `WEB_CONCURRENCY` | `1`                     | Workers de Gunicorn (default `1`) |
| `GUNICORN_BACKLOG` | `64`                   | Backlog acotado del socket de Gunicorn |
| `CONSUL_ENABLED` | `false`                  | Activa el registro en Consul y la lectura de KV |
| `CONSUL_HTTP_ADDR` | `http://127.0.0.1:8500` | URL base del agente de Consul |
| `CONSUL_HTTP_TOKEN` | vacío                  | Token ACL; se envía como `X-Consul-Token` en todas las llamadas |
| `CONSUL_HTTP_TIMEOUT` | `2`                  | Timeout de las llamadas HTTP a Consul (segundos) |

Gunicorn (servidor): `WEB_CONCURRENCY` (workers, default `1`) y
`GUNICORN_BACKLOG` (backlog de socket acotado, default `64`) en
`gunicorn.conf.py`. La admisión total por contenedor es
`WEB_CONCURRENCY × MAX_CONCURRENCY` (1 × 1 = 1 con los defaults, dimensionado
para 1 CPU / 1 GB porque la extracción es CPU-bound).

## Integración con Consul y Traefik

El cliente vive en `src/pdf_extractext_extractor/discovery.py` y usa solo la
librería estándar (`urllib.request`, `socket`, `json`, `base64`): no agrega
dependencias de runtime. Todas las llamadas envían `X-Consul-Token` cuando
`CONSUL_HTTP_TOKEN` está definido y respetan `CONSUL_HTTP_TIMEOUT`.

Flujo de registro:

1. `on_starting` corre en el master **antes de forkear** los workers. Lee
   `GET /v1/kv/pdf-extractext/config/extraction/?recurse` y aplica
   `MAX_UPLOAD_BYTES`, `MAX_CONCURRENCY` y `RETRY_AFTER_SECONDS` con
   precedencia **env > KV > default**. Los workers heredan el entorno.
2. `when_ready` registra una sola vez con
   `PUT /v1/agent/service/register`. El ID es `extraction-<hostname>`, la
   `Address` se obtiene con un socket UDP hacia `CONSUL_HTTP_ADDR` (nunca se
   hardcodea localhost), el `Port` es `8001` y el check apunta a
   `http://<address>:8001/readyz` con `Interval: 10s`, `Timeout: 2s` y
   `DeregisterCriticalServiceAfter: 1m`.
3. `on_exit` ejecuta
   `PUT /v1/agent/service/deregister/<ID>` desde el master.

Los hooks se registran en el master de Gunicorn y no en el `lifespan` de
FastAPI para evitar registros duplicados cuando `WEB_CONCURRENCY > 1`. Si
Consul está caído, el arranque continúa: el registro reintenta con backoff y
la lectura de KV cae a los defaults con un warning.

Tags publicados (las directivas de Traefik viven **solo en Tags** porque el
provider `consulCatalog` las lee de ahí y Consul rechaza claves con puntos en
`Meta`, que queda reducido a `version` y `commit`):

```
traefik.enable=true
traefik.http.routers.extraction.rule=Host(`extraction.pdf-extractext.localhost`)
traefik.http.routers.extraction.entrypoints=internal
traefik.http.routers.extraction.middlewares=circuit-breaker@file
traefik.http.services.extraction.loadbalancer.server.port=8001
```

El middleware `circuit-breaker@file` activa el Circuit Breaker de Traefik
(definido como file provider en `pdf-extractext-infrastructure`): si el
extractor satura con errores 5xx, Traefik corta el tráfico hacia él en vez
de acumular peticiones que romperían el timeout de los clientes (30s en
k6/Vegeta). Se combina con el backpressure local (503 + `Retry-After` de
`AdmissionMiddleware`): el rechazo inmediato evita colas indefinidas y el
Circuit Breaker evita mandar tráfico a una instancia que ya está fallando.

Ejemplo de arranque con Consul habilitado:

```bash
CONSUL_ENABLED=true \
CONSUL_HTTP_ADDR=http://consul:8500 \
CONSUL_HTTP_TOKEN=mi-token \
GIT_COMMIT=$(git rev-parse --short HEAD) \
uv run gunicorn pdf_extractext_extractor.main:app -c gunicorn.conf.py
```

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
| `422` | `INVALID_PDF_CONTENT` | El contenido no es un PDF válido/procesable (incluye PDF protegido con contraseña). |
| `500` | `INTERNAL_ERROR` | Fallo interno de procesamiento. |
| `503` | `SERVICE_OVERLOADED` | Control de admisión saturado (backpressure, rechazo inmediato) — siempre con header `Retry-After`. |

```bash
curl -F "file=@documento.pdf" http://localhost:8001/extract
```

## Desarrollo

```bash
# Instalar dependencias
uv sync

# Ejecutar la aplicación (desarrollo)
uv run uvicorn pdf_extractext_extractor.main:app --app-dir src --port 8001 --reload

# Ejecutar como en producción (Gunicorn + workers Uvicorn)
uv run gunicorn pdf_extractext_extractor.main:app -c gunicorn.conf.py

# Health check
curl http://localhost:8001/health
```

## Tests

```bash
# Gate único del proyecto (unitarios + integración)
make test

# Cobertura (el umbral mínimo es 80 %)
uv run pytest -q --cov
```

`make test` ejecuta `uv run pytest -q`; `pytest-cov` es una dependencia de
desarrollo y el umbral se configura en `pyproject.toml`.

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
├── pyproject.toml                    # Dependencias, pytest y umbral de cobertura
├── .env.example                      # Variables de entorno documentadas
├── Dockerfile                        # Multi-stage, no-root, healthcheck
├── docker-compose.yml                # Smoke local: límites 1 CPU / 1 GB, sin ports
├── gunicorn.conf.py                  # Workers, hooks Consul y KV antes del fork
├── Makefile                          # test / test-cov / smoke
├── src/
│   └── pdf_extractext_extractor/
│       ├── config.py                 # Settings por variables de entorno
│       ├── discovery.py              # Cliente Consul stdlib + payload Traefik
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
└── tests/                            # unitarios, hooks Gunicorn, KV e integration/
```
