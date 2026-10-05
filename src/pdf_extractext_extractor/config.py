"""Configuración del servicio basada en variables de entorno."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación leída desde variables de entorno."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "pdf-extractext-extractor"
    app_version: str = "0.1.0"
    port: int = 8000
    max_upload_bytes: int = 64 * 1024 * 1024
    # Admisión por proceso: 1 extracción simultánea por worker (Issue #6).
    max_concurrency: int = 1
    retry_after_seconds: int = 1


settings = Settings()
