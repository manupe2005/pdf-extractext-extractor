"""Fase Verde — Contrato del Extraction Service (Clean Architecture).

1. El endpoint GET /health responde HTTP 200 (liveness provisional).
2. El árbol src/app NO contiene dependencias de persistencia ni MongoDB
   (prohibición absoluta del bootstrap).
"""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SRC_APP_DIR = Path(__file__).resolve().parents[2] / "src" / "app"

# Imports prohibidos: cero persistencia/MongoDB (el motor PDF vive en infrastructure).
FORBIDDEN_MODULES = ("pymongo", "motor", "mongodb", "bson")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


class TestHealthEndpoint:
    """Contrato del liveness provisional."""

    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200

    def test_health_payload_is_stable(self, client: TestClient) -> None:
        payload = client.get("/health").json()

        assert payload["status"] == "ok"


class TestNoPersistenceDependencies:
    """Introspección estática: garantiza la ausencia absoluta de imports
    de persistencia/MongoDB en todos los módulos de src/app."""

    @staticmethod
    def _python_files() -> list[Path]:
        files = sorted(SRC_APP_DIR.rglob("*.py"))
        assert files, f"Se esperaban módulos en {SRC_APP_DIR}"
        return files

    def test_app_tree_contains_no_forbidden_imports(self) -> None:
        for file_path in self._python_files():
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
                        f"{file_path.relative_to(SRC_APP_DIR)} importa {name!r}, "
                        "prohibido en esta fase"
                    )
