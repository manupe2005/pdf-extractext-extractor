"""Fixtures de la capa API para POST /extract (Issue #5)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from pdf_extractext_extractor.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def pdf_bytes(valid_pdf_multipart: dict[str, Any]) -> bytes:
    """Bytes del PDF inyectado en el multipart raíz (misma identidad)."""
    return valid_pdf_multipart["files"]["file"][1]
