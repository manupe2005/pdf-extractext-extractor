"""Tests del endpoint /health y guardas de arquitectura del paquete plano.

1. El endpoint GET /health responde HTTP 200 con payload estable.
2. El paquete src/pdf_extractext_extractor no contiene dependencias de
   persistencia ni motor de PDF (prohibición absoluta de esta fase).
"""

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.main import app

SRC_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "pdf_extractext_extractor"

FORBIDDEN_MODULES = ("pymongo", "motor", "mongodb", "bson")


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


def test_readyz_returns_ok() -> None:
    """Readiness para healthchecks de Docker/Traefik (Issue #12)."""
    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_package_contains_no_forbidden_imports() -> None:
    files = sorted(SRC_PACKAGE_DIR.rglob("*.py"))
    assert files, f"Se esperaban módulos en {SRC_PACKAGE_DIR}"
    for file_path in files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert root not in FORBIDDEN_MODULES, (
                    f"{file_path.name} importa {name!r}, prohibido en esta fase"
                )
