"""Issue #10 — Verificación E2E del flujo upload (contrato con API Service).

Valida el borde público del Extraction Service:

1. Flujo feliz: POST multipart/form-data con un PDF real responde el
   contrato C1 extendido: {filename, extracted_text, checksum, content, page_count}.
2. Matriz de errores: traducción correcta a 400 / 422 / 500 / 503 con
   envelope contractual {code, message}.
3. Propagación end-to-end del header X-Request-ID.
"""

import hashlib
import uuid

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api.extraction import get_admission_limiter, get_pdf_extractor
from app.main import app

PDF_FILENAME = "cabras.pdf"
PDF_TEXT = "Hola Cabras"


def _build_pdf_bytes(text: str = PDF_TEXT) -> bytes:
    """Genera un PDF real de una página con texto, completamente en memoria."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def pdf_bytes() -> bytes:
    return _build_pdf_bytes()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestUploadHappyPath:
    """Contrato C1 extendido del flujo feliz (multipart/form-data, campo `file`)."""

    def test_upload_pdf_returns_200_with_extended_contract(
        self, client: TestClient, pdf_bytes: bytes
    ) -> None:
        response = client.post(
            "/extract",
            files={"file": (PDF_FILENAME, pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["filename"] == PDF_FILENAME
        assert PDF_TEXT in payload["extracted_text"]
        assert payload["checksum"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert PDF_TEXT in payload["content"]
        assert payload["page_count"] == 1


class TestErrorMatrix:
    """Traducción de errores en el borde público: 400/422/500/503 con {code, message}."""

    def test_missing_file_field_returns_400(self, client: TestClient) -> None:
        response = client.post("/extract", files={})

        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "bad_request"
        assert body["message"]

    def test_corrupted_pdf_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            files={"file": (PDF_FILENAME, b"esto no es un pdf", "application/pdf")},
        )

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "unprocessable_entity"
        assert body["message"]

    def test_internal_extractor_failure_returns_500(
        self, client: TestClient, pdf_bytes: bytes
    ) -> None:
        class ExplodingExtractor:
            def extract(self, data: bytes) -> tuple[str, int]:
                raise RuntimeError("boom")

        app.dependency_overrides[get_pdf_extractor] = ExplodingExtractor
        response = client.post(
            "/extract",
            files={"file": (PDF_FILENAME, pdf_bytes, "application/pdf")},
        )
        app.dependency_overrides.pop(get_pdf_extractor, None)

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "internal_error"
        assert body["message"]

    def test_saturated_service_returns_503(
        self, client: TestClient, pdf_bytes: bytes
    ) -> None:
        class SaturatedLimiter:
            async def __aenter__(self) -> object:
                from app.domain.errors import ServiceSaturatedError

                raise ServiceSaturatedError("Servicio saturado, reintentar luego")

            async def __aexit__(self, *exc) -> None:
                return None

        app.dependency_overrides[get_admission_limiter] = lambda: SaturatedLimiter()
        try:
            response = client.post(
                "/extract",
                files={"file": (PDF_FILENAME, pdf_bytes, "application/pdf")},
            )

            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "service_unavailable"
            assert body["message"]
            assert response.headers.get("Retry-After")
        finally:
            app.dependency_overrides.pop(get_admission_limiter, None)


class TestRequestIdPropagation:
    """El header X-Request-ID se recibe y se devuelve intacto end-to-end."""

    def test_x_request_id_propagates_end_to_end(
        self, client: TestClient, pdf_bytes: bytes
    ) -> None:
        request_id = str(uuid.uuid4())
        response = client.post(
            "/extract",
            files={"file": (PDF_FILENAME, pdf_bytes, "application/pdf")},
            headers={"X-Request-ID": request_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == request_id

    def test_x_request_id_propagates_even_on_error(self, client: TestClient) -> None:
        request_id = str(uuid.uuid4())
        response = client.post(
            "/extract",
            files={"file": (PDF_FILENAME, b"corrupto", "application/pdf")},
            headers={"X-Request-ID": request_id},
        )

        assert response.status_code == 422
        assert response.headers["X-Request-ID"] == request_id
