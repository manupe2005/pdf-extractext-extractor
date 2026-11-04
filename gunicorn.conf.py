"""Gunicorn: workers por env y registro de la instancia en Consul."""

import logging
import os
import time

from pdf_extractext_extractor import discovery

logger = logging.getLogger(__name__)

workers = int(os.getenv("WEB_CONCURRENCY", "1"))  # la extracción es CPU-bound
worker_class = "uvicorn.workers.UvicornWorker"
bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
backlog = int(os.getenv("GUNICORN_BACKLOG", "64"))
graceful_timeout = 30

SERVICE_PORT = 8001
REGISTER_ATTEMPTS = 3
RETRY_BASE_SECONDS = 0.5
_registered_service_id: str | None = None


def _consul_enabled() -> bool:
    return os.getenv("CONSUL_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _service_version() -> str:
    return os.getenv("APP_VERSION", "0.1.0")


def _service_commit() -> str:
    return os.getenv("GIT_COMMIT") or os.getenv("COMMIT") or "unknown"


def _registration_payload(address: str) -> dict:
    return discovery.build_service_registration(
        service_id=discovery.service_id(),
        address=address,
        port=SERVICE_PORT,
        version=_service_version(),
        commit=_service_commit(),
    )


def when_ready(server) -> None:
    """Registra la instancia una sola vez desde el master."""
    global _registered_service_id
    if not _consul_enabled() or _registered_service_id is not None:
        return

    client = discovery.ConsulClient()
    try:
        address = discovery.resolve_local_address(client.http_addr)
    except discovery.ConsulError as exc:
        logger.warning("No se pudo resolver la IP local para Consul: %s", exc)
        return

    payload = _registration_payload(address)
    service_id = payload["ID"]
    for attempt in range(1, REGISTER_ATTEMPTS + 1):
        try:
            client.register(payload)
        except discovery.ConsulError as exc:
            if attempt == REGISTER_ATTEMPTS:
                logger.warning(
                    "No se pudo registrar en Consul tras %d intentos: %s",
                    attempt,
                    exc,
                )
                return
            time.sleep(RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
        else:
            _registered_service_id = service_id
            logger.info("Instancia registrada en Consul como %s", service_id)
            return


def on_exit(server) -> None:
    """Deregistra la instancia desde el master al apagar."""
    global _registered_service_id
    if _registered_service_id is None:
        return

    service_id = _registered_service_id
    try:
        discovery.ConsulClient().deregister(service_id)
        logger.info("Instancia deregistrada de Consul: %s", service_id)
    except discovery.ConsulError as exc:
        logger.warning("No se pudo deregistrar %s de Consul: %s", service_id, exc)
    finally:
        _registered_service_id = None
