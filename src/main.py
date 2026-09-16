"""Punto de entrada de la aplicación FastAPI."""

from fastapi import FastAPI

from src.config import settings


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI."""
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    return app


app = create_app()
