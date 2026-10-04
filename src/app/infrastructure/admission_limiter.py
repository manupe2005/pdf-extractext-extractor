"""Adapter de AdmissionLimiter: semáforo asyncio con timeout corto (fail-fast)."""

import asyncio

from app.domain.errors import ServiceSaturatedError


class SemaphoreAdmissionLimiter:
    """N slots de admisión por proceso worker."""

    def __init__(self, slots: int, timeout_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(slots)
        self._timeout_seconds = timeout_seconds

    async def __aenter__(self) -> "SemaphoreAdmissionLimiter":
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self._timeout_seconds
            )
        except TimeoutError:
            raise ServiceSaturatedError("Servicio saturado, reintentar luego") from None
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._semaphore.release()
