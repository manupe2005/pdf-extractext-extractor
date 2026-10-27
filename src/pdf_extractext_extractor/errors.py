"""Catálogo de errores de la API."""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pdf_extractext_extractor.constants import (
    INTERNAL_ERROR,
    INVALID_PDF_CONTENT,
    INVALID_REQUEST,
    TITLE_INTERNAL_ERROR,
    TITLE_INVALID_PDF_CONTENT,
    TITLE_INVALID_REQUEST,
    TYPE_INTERNAL_ERROR,
    TYPE_INVALID_PDF_CONTENT,
    TYPE_INVALID_REQUEST,
)
from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)


def build_error_response(
    status_code: int,
    code: str,
    detail: str,
    headers: dict[str, str] | None = None,
    type_: str | None = None,
    title: str | None = None,
) -> JSONResponse:
    """Construye la respuesta de error en formato RFC 9457."""
    if type_ is None:
        if code == INVALID_REQUEST:
            type_ = TYPE_INVALID_REQUEST
        elif code == INVALID_PDF_CONTENT:
            type_ = TYPE_INVALID_PDF_CONTENT
        elif code == INTERNAL_ERROR:
            type_ = TYPE_INTERNAL_ERROR
        else:
            type_ = "about:blank"
    if title is None:
        if code == INVALID_REQUEST:
            title = TITLE_INVALID_REQUEST
        elif code == INVALID_PDF_CONTENT:
            title = TITLE_INVALID_PDF_CONTENT
        elif code == INTERNAL_ERROR:
            title = TITLE_INTERNAL_ERROR
        else:
            title = detail
    content: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
    }
    resp_headers = {"content-type": "application/problem+json"}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(status_code=status_code, content=content, headers=resp_headers)


class InvalidRequest(Exception):
    """Fallo estructural de la petición: el cliente envió algo inválido."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def invalid_request_handler(request: Request, exc: InvalidRequest) -> JSONResponse:
    return build_error_response(400, INVALID_REQUEST, exc.message)


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return build_error_response(400, INVALID_REQUEST, "Petición inválida.")


async def invalid_pdf_content_handler(
    request: Request, exc: InvalidPDFContentError
) -> JSONResponse:
    return build_error_response(422, INVALID_PDF_CONTENT, str(exc))


async def internal_processing_error_handler(
    request: Request, exc: InternalProcessingError
) -> JSONResponse:
    return build_error_response(500, INTERNAL_ERROR, str(exc))
