"""Catálogo de errores de la API (Issue #5).

Envelope estricto para todas las fallas:

    400 INVALID_REQUEST      -> multipart ausente / malformado / vacío
    422 INVALID_PDF_CONTENT  -> InvalidPDFContentError del dominio
    500 INTERNAL_ERROR       -> InternalProcessingError del dominio

Prohibido emitir 415, 404 o 409 desde estas rutas.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)


class InvalidRequest(Exception):
    """Fallo estructural de la petición: el cliente envió algo inválido."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def invalid_request_handler(request: Request, exc: InvalidRequest) -> JSONResponse:
    """Traduce InvalidRequest al contrato de error 400 exacto."""
    return JSONResponse(
        status_code=400,
        content={"code": "INVALID_REQUEST", "message": exc.message},
    )


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Sobrescribe el 422 genérico de FastAPI/Pydantic: aquí es un 400.

    El catálogo del servicio reserva 422 exclusivamente para
    INVALID_PDF_CONTENT (fallo de parseo del PDF), por lo que un error de
    validación del request se traduce a INVALID_REQUEST.
    """
    return JSONResponse(
        status_code=400,
        content={"code": "INVALID_REQUEST", "message": "Petición inválida."},
    )


async def invalid_pdf_content_handler(
    request: Request, exc: InvalidPDFContentError
) -> JSONResponse:
    """Traduce el error de dominio de PDF inválido a 422 INVALID_PDF_CONTENT."""
    return JSONResponse(
        status_code=422,
        content={"code": "INVALID_PDF_CONTENT", "message": str(exc)},
    )


async def internal_processing_error_handler(
    request: Request, exc: InternalProcessingError
) -> JSONResponse:
    """Traduce el fallo inesperado del dominio a 500 INTERNAL_ERROR."""
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": str(exc)},
    )
