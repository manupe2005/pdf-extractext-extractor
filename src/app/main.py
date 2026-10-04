"""Punto de entrada de la aplicación FastAPI."""

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api.health import router as health_router
from app.core.config import settings

logger = logging.getLogger("app")

REQUEST_ID_HEADER = "X-Request-ID"


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Propaga el header X-Request-ID: lo genera si falta y lo devuelve en la respuesta."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id
    logger.info(
        "request_started",
        extra={"request_id": request_id, "method": request.method, "path": request.url.path},
    )
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI."""
    application = FastAPI(title=settings.app_name, version=settings.app_version)
    application.middleware("http")(request_id_middleware)
    application.include_router(health_router)
    return application


app = create_app()
