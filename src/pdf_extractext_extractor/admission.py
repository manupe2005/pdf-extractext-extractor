"""Control de admisión con backpressure (Issue #6).

Semáforo de admisión por proceso sobre la ruta protegida (`/extract`).
La adquisición es no bloqueante: `locked()` + `acquire()` sin await
intermedio es atómico en el event loop, por lo que sin slot libre se
rechaza de inmediato con 503 + Retry-After en lugar de acumular espera.

Las rutas no protegidas (`/health`) nunca consumen slots: el liveness
no debe ahogarse bajo saturación.
"""

import asyncio
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class AdmissionMiddleware(BaseHTTPMiddleware):
    """Rechaza con 503 inmediato cuando no hay capacidad de admisión."""

    def __init__(
        self,
        app: ASGIApp,
        max_concurrency: int,
        retry_after: int,
        protected_path: str = "/extract",
    ) -> None:
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.retry_after = retry_after
        self.protected_path = protected_path
        self.rejections = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path != self.protected_path:
            return await call_next(request)

        if self.semaphore.locked():
            self.rejections += 1
            logger.warning(
                "rechazo 503 por saturación (rechazos acumulados=%d)", self.rejections
            )
            return JSONResponse(
                status_code=503,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "Servicio saturado. Reintente más tarde.",
                },
                headers={"Retry-After": str(self.retry_after)},
            )

        await self.semaphore.acquire()
        try:
            return await call_next(request)
        finally:
            self.semaphore.release()
