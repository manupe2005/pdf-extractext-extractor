"""Matriz de traducción de errores al envelope contractual {code, message}."""

import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    ExtractionServiceError,
    InvalidPDFFormatError,
    ServiceSaturatedError,
)

logger = logging.getLogger("app")

RETRY_AFTER_SECONDS = "1"

STATUS_BY_DOMAIN_ERROR: Mapping[type[ExtractionServiceError], int] = {
    InvalidPDFFormatError: 422,
    ServiceSaturatedError: 503,
}

CODE_BY_HTTP_STATUS: Mapping[int, str] = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
}


def register_error_handlers(application: FastAPI) -> None:
    """Registra en el borde los handlers de la matriz de errores."""

    @application.exception_handler(ExtractionServiceError)
    async def domain_error_handler(
        request: Request, exc: ExtractionServiceError
    ) -> JSONResponse:
        status_code = STATUS_BY_DOMAIN_ERROR.get(type(exc), 500)
        headers = {"Retry-After": RETRY_AFTER_SECONDS} if status_code == 503 else None
        return JSONResponse(
            status_code=status_code,
            content={"code": exc.code, "message": exc.message},
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "code": "bad_request",
                "message": "La petición es inválida: falta el campo 'file' o el "
                "multipart/form-data es incorrecto.",
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = CODE_BY_HTTP_STATUS.get(exc.status_code, f"http_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail)},
            headers=getattr(exc, "headers", None),
        )

    @application.exception_handler(Exception)
    async def internal_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_error",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Error interno al procesar el PDF.",
            },
        )
