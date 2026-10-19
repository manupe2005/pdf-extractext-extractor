"""Configuración del servicio basada en variables de entorno."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "pdf-extractext-extractor"
    app_version: str = "0.1.0"
    max_upload_bytes: int = 64 * 1024 * 1024
    max_concurrency: int = 1
    retry_after_seconds: int = 1


settings = Settings()
