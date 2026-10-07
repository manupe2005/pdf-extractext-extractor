"""Punto de entrada de la aplicación FastAPI."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from pdf_extractext_extractor.admission import AdmissionMiddleware
from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)
from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import (
    InvalidRequest,
    internal_processing_error_handler,
    invalid_pdf_content_handler,
    invalid_request_handler,
    request_validation_handler,
)
from pdf_extractext_extractor.extraction import router as extraction_router


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI."""
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        AdmissionMiddleware,
        max_concurrency=settings.max_concurrency,
        retry_after=settings.retry_after_seconds,
    )
    app.add_exception_handler(InvalidRequest, invalid_request_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(InvalidPDFContentError, invalid_pdf_content_handler)
    app.add_exception_handler(
        InternalProcessingError, internal_processing_error_handler
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    @app.get("/readyz", tags=["Health"])
    def readyz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(extraction_router)
    return app


app = create_app()
