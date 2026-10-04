"""Puertos (interfaces) que el dominio expone a la infraestructura."""

from typing import Protocol


class PDFExtractor(Protocol):
    """Extrae el texto de un PDF; devuelve (texto, cantidad de páginas)."""

    def extract(self, data: bytes) -> tuple[str, int]: ...


class AdmissionLimiter(Protocol):
    """Limitador de admisión: async context manager de backpressure."""

    async def __aenter__(self) -> object: ...

    async def __aexit__(self, *exc: object) -> None: ...
