"""Tests para el endpoint /health."""

from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == settings.app_name
    assert payload["version"] == settings.app_version
