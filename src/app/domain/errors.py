"""Errores de dominio del Extraction Service.

La clasificación HTTP (R3) vive en el borde de la API, no en el dominio.
"""

from typing import ClassVar


class ExtractionServiceError(Exception):
    """Base de los errores de dominio del servicio de extracción."""

    code: ClassVar[str] = "extraction_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidPDFFormatError(ExtractionServiceError):
    """El contenido recibido no es un PDF procesable."""

    code: ClassVar[str] = "unprocessable_entity"


class ServiceSaturatedError(ExtractionServiceError):
    """El servicio no admite más trabajo concurrente."""

    code: ClassVar[str] = "service_unavailable"
