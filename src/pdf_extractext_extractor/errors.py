"""Errores de la API en RFC 9457 problem+json (catálogo cerrado de codes).

400 INVALID_REQUEST / 422 INVALID_PDF_CONTENT / 500 INTERNAL_ERROR /
503 SERVICE_OVERLOADED. Prohibido emitir 415, 404 o 409.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"

# Catálogo cerrado: URN y title por code (RFC 9457 §3).
PROBLEM_CATALOG: dict[str, tuple[str, str]] = {
    "INVALID_REQUEST": ("invalid-request", "Petición inválida"),
    "INVALID_PDF_CONTENT": ("invalid-pdf-content", "Contenido PDF inválido"),
    "INTERNAL_ERROR": ("internal-error", "Error interno del servidor"),
    "SERVICE_OVERLOADED": ("service-overloaded", "Servicio saturado"),
}


def problem_response(status: int, code: str, detail: str, headers=None) -> JSONResponse:
    """Construye la respuesta problem+json del catálogo dado."""
    slug, title = PROBLEM_CATALOG[code]
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        content={
            "type": f"urn:pdf-extractext:{slug}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
        },
        headers=headers,
    )


class InvalidRequest(Exception):
    """Fallo estructural de la petición: el cliente envió algo inválido."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def invalid_request_handler(request: Request, exc: InvalidRequest) -> JSONResponse:
    """Traduce InvalidRequest al problem 400 exacto."""
    return problem_response(400, "INVALID_REQUEST", exc.message)


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Traduce la validación del request a 400: el 422 es solo del PDF."""
    return problem_response(400, "INVALID_REQUEST", "Petición inválida.")


async def invalid_pdf_content_handler(
    request: Request, exc: InvalidPDFContentError
) -> JSONResponse:
    """Traduce el error de dominio de PDF inválido a 422."""
    return problem_response(422, "INVALID_PDF_CONTENT", str(exc))


async def internal_processing_error_handler(
    request: Request, exc: InternalProcessingError
) -> JSONResponse:
    """Traduce el fallo inesperado del dominio a 500."""
    return problem_response(500, "INTERNAL_ERROR", str(exc))
