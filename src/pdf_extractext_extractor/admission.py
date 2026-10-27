"""Control de admisión con backpressure."""

import asyncio
import json
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from pdf_extractext_extractor.constants import (
    SERVICE_OVERLOADED,
    TITLE_SERVICE_OVERLOADED,
    TYPE_SERVICE_OVERLOADED,
)

logger = logging.getLogger(__name__)


class AdmissionMiddleware(BaseHTTPMiddleware):
    """Rechaza con 503 inmediato cuando no hay capacidad."""

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
            body = {
                "type": TYPE_SERVICE_OVERLOADED,
                "title": TITLE_SERVICE_OVERLOADED,
                "status": 503,
                "detail": "Servicio saturado. Reintente más tarde.",
                "code": SERVICE_OVERLOADED,
            }
            return Response(
                content=json.dumps(body),
                status_code=503,
                media_type="application/problem+json",
                headers={"Retry-After": str(self.retry_after)},
            )

        await self.semaphore.acquire()
        try:
            return await call_next(request)
        finally:
            self.semaphore.release()
