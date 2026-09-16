# Implementation Plan: Bootstrap de pdf-extractext-extraction

## Overview

Base mínima y ejecutable del microservicio: FastAPI + uv, `GET /health`, configuración por variables de entorno, test unitario, Dockerfile y README. Sin lógica de negocio (sin extracción de PDF, checksum, Persistence, etc.).

## Architecture Decisions

- **Python 3.12 + FastAPI + Uvicorn**, gestionado con **uv** (`uv sync`, `uv run`).
- Estructura plana en `src/pdf_extractext_extractor/`: sin capas ni abstracciones.
- Configuración con `pydantic-settings` (`APP_NAME`, `APP_VERSION`, `PORT`).
- Dependencias mínimas: `fastapi`, `uvicorn[standard]`, `pydantic-settings`; dev: `pytest`, `httpx`.

## Task List

### Phase 1: Foundation
- [x] Task 1: Configuración del proyecto (`pyproject.toml`, `.gitignore`, `.dockerignore`)
- [x] Task 2: Aplicación FastAPI mínima (`src/`: `__init__.py`, `config.py`, `main.py` con `GET /health`)

### Phase 2: Verificación y empaquetado
- [x] Task 3: Test unitario de `/health` (`tests/test_health.py`)
- [x] Task 4: `Dockerfile` + `README.md`

### Checkpoint: Complete
- [x] `uv run pytest` pasa
- [x] La app arranca con uvicorn y `/health` responde 200
- [ ] Commit inicial (pendiente, a pedido del usuario)

## Fuera de alcance (etapas futuras)

Extracción de PDF (PyMuPDF), checksum, Persistence, clientes a otros servicios, endpoints de negocio, Docker Compose, Traefik, MongoDB, Dragonfly, tests de integración.

## Open Questions

- Nombre definitivo del paquete: confirmado `pdf_extractext_extractor`.
