"""Punto de entrada de la aplicación FastAPI."""

from fastapi import FastAPI

from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import InvalidRequest, invalid_request_handler
from pdf_extractext_extractor.extraction import router as extraction_router


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI."""
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_exception_handler(InvalidRequest, invalid_request_handler)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    app.include_router(extraction_router)
    return app


app = create_app()
