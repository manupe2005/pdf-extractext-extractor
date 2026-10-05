"""Tests de POST /extract (Issue #2): recepción multipart 100% en memoria.

Contrato de error estructural exacto:

    400 -> {"code": "INVALID_REQUEST", "message": "<detalle>"}
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import PDF_BYTES, PDF_FILENAME
from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def assert_invalid_request(response: Any) -> None:
    """El cuerpo de error debe ser exactamente {"code", "message"} con 400."""
    assert response.status_code == 400
    payload = response.json()
    assert set(payload) == {"code", "message"}
    assert payload["code"] == "INVALID_REQUEST"
    assert isinstance(payload["message"], str) and payload["message"]


class TestExtractReception:
    """Recepción válida: 200 con filename íntegro y contrato combinado (C1+TP)."""

    def test_receives_file_and_answers_filename_and_size(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 200
        assert response.json()["filename"] == PDF_FILENAME

    def test_filename_is_taken_verbatim_from_the_request(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        valid_pdf_multipart["files"]["file"] = (
            "anexo B cabras.pdf",
            PDF_BYTES,
            "application/pdf",
        )

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 200
        assert response.json()["filename"] == "anexo B cabras.pdf"


class TestInMemoryReception:
    """Invariante 100% en memoria: ningún archivo rueda a disco."""

    def test_file_over_spool_threshold_never_touches_disk(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        """Un archivo de 2 MB no debe disparar el volcado a disco de
        SpooledTemporaryFile (umbral por defecto de Starlette: 1 MB)."""

        def fail_if_rolled(self: Any) -> None:
            raise AssertionError("SpooledTemporaryFile rodó a disco")

        monkeypatch.setattr("tempfile.SpooledTemporaryFile.rollover", fail_if_rolled)
        big_bytes = PDF_BYTES + b"0" * (2 * 1024 * 1024 - len(PDF_BYTES))
        valid_pdf_multipart["files"]["file"] = (PDF_FILENAME, big_bytes, "application/pdf")

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 200
        assert response.json()["filename"] == PDF_FILENAME


class TestExtractStructuralValidation:
    """Toda falla estructural responde 400 con el contrato exacto."""

    def test_rejects_request_without_multipart_content_type(
        self, client: TestClient
    ) -> None:
        response = client.post("/extract", json={"file": "no soy un archivo"})

        assert_invalid_request(response)
        assert "multipart" in response.json()["message"]

    def test_rejects_missing_file_field(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            files={"otro": ("a.pdf", PDF_BYTES, "application/pdf")},
        )

        assert_invalid_request(response)
        assert "'file'" in response.json()["message"]

    def test_rejects_file_field_that_is_not_a_file(self, client: TestClient) -> None:
        response = client.post("/extract", data={"file": "texto plano"})

        assert_invalid_request(response)

    def test_rejects_empty_file(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            files={"file": ("vacio.pdf", b"", "application/pdf")},
        )

        assert_invalid_request(response)

    def test_rejects_multipart_without_boundary(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            content=b"--x\r\n\r\n--x--\r\n",
            headers={"Content-Type": "multipart/form-data"},
        )

        assert_invalid_request(response)

    def test_rejects_malformed_multipart_body(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            content=b"\x00\x01esto no es un multipart valido",
            headers={"Content-Type": "multipart/form-data; boundary=boundary123"},
        )

        assert_invalid_request(response)


class TestExtractDefensiveSizeLimit:
    """Límite defensivo: protege la memoria rechazando cuerpos oversize."""

    def test_rejects_body_over_the_limit(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "max_upload_bytes", 64)

        response = client.post(
            "/extract",
            files={"file": ("grande.pdf", b"a" * 256, "application/pdf")},
        )

        assert_invalid_request(response)
        assert "límite" in response.json()["message"]
