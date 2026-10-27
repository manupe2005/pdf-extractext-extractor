"""Contrato E2E que la API Service consume de Extraction.

Ejercita POST /extract como lo hará la API vía Traefik interno:
200 con {filename, extracted_text, checksum, content, page_count} y errores
problem+json (400 INVALID_REQUEST / 422 INVALID_PDF_CONTENT /
500 INTERNAL_ERROR / 503 SERVICE_OVERLOADED + Retry-After). El header
X-Request-ID se tolera; su reflejo futuro queda como xfail.
"""

import asyncio
import hashlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from pdf_extractext_extractor.admission import AdmissionMiddleware
from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)
from pdf_extractext_extractor.main import create_app

EXTRACTOR_PATCH_TARGET = "pdf_extractext_extractor.domain.extractor.PyMuPDFExtractor.extract"
EXPECTED_SUCCESS_KEYS = {
    "filename",
    "extracted_text",
    "checksum",
    "content",
    "page_count",
}
PROBLEM_KEYS = {"type", "title", "status", "detail", "code"}


@pytest.fixture()
def client() -> TestClient:
    """Cliente HTTP de la app completa, como el que usaría la API."""
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Flujo feliz: la API recibe exactamente el contrato extendido
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_valid_pdf_with_request_id_returns_200_and_contract(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        response = client.post(
            "/extract",
            headers={"X-Request-ID": "req-e2e-001"},
            **valid_pdf_multipart,
        )

        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == EXPECTED_SUCCESS_KEYS
        assert isinstance(payload["filename"], str)
        assert isinstance(payload["extracted_text"], str)
        assert isinstance(payload["checksum"], str)
        assert isinstance(payload["content"], str)
        assert isinstance(payload["page_count"], int)
        # Regla contractual: extracted_text y content son el mismo string.
        assert payload["extracted_text"] == payload["content"]

    def test_checksum_matches_sha256_of_original_bytes(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        pdf_bytes = valid_pdf_multipart["files"]["file"][1]
        payload = client.post("/extract", **valid_pdf_multipart).json()
        assert payload["checksum"] == hashlib.sha256(pdf_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Matriz de errores: envelopes y status codes exactos
# ---------------------------------------------------------------------------


class TestErrorMatrix:
    def test_non_multipart_body_returns_400_invalid_request(
        self, client: TestClient
    ) -> None:
        response = client.post("/extract", content=b"%PDF-1.4 binario directo")

        assert response.status_code == 400
        payload = response.json()
        assert set(payload) == PROBLEM_KEYS
        assert payload["code"] == "INVALID_REQUEST"

    def test_multipart_without_file_field_returns_400(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/extract",
            files={"otro_campo": ("x.pdf", b"%PDF-x", "application/pdf")},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"

    def test_non_pdf_content_returns_422_invalid_pdf_content(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/extract",
            files={"file": ("no-es-pdf.pdf", b"texto plano", "application/pdf")},
        )

        assert response.status_code == 422
        payload = response.json()
        assert set(payload) == PROBLEM_KEYS
        assert payload["code"] == "INVALID_PDF_CONTENT"

    def test_domain_invalid_pdf_error_maps_to_422(
        self,
        client: TestClient,
        valid_pdf_multipart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_invalid(self, _pdf_bytes: bytes):
            raise InvalidPDFContentError("El contenido recibido no es un PDF válido")

        monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _raise_invalid)

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 422
        assert response.json()["detail"] == "El contenido recibido no es un PDF válido"
        assert response.json()["code"] == "INVALID_PDF_CONTENT"

    def test_internal_processing_error_maps_to_500(
        self,
        client: TestClient,
        valid_pdf_multipart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_internal(self, _pdf_bytes: bytes):
            raise InternalProcessingError("Fallo inesperado procesando el PDF")

        monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _raise_internal)

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 500
        assert response.json()["detail"] == "Fallo inesperado procesando el PDF"
        assert response.json()["code"] == "INTERNAL_ERROR"

    def test_admission_saturation_returns_503_with_retry_after(self) -> None:
        async def scenario() -> None:
            middleware = AdmissionMiddleware(
                lambda _req: None, max_concurrency=1, retry_after=3
            )
            await middleware.semaphore.acquire()  # slot ocupado

            scope = {
                "type": "http",
                "method": "POST",
                "path": "/extract",
                "query_string": b"",
                "headers": [],
                "scheme": "http",
                "server": ("testserver", 80),
            }
            response = await middleware.dispatch(
                Request(scope), lambda _req: None
            )

            assert response.status_code == 503
            assert json.loads(response.body) == {
                "type": "urn:pdf-extractext:service-overloaded",
                "title": "Servicio saturado",
                "status": 503,
                "detail": "Servicio saturado. Reintente más tarde.",
                "code": "SERVICE_OVERLOADED",
            }
            assert response.headers["retry-after"] == "3"

        asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Propagación de X-Request-ID: comportamiento actual y garantía futura
# ---------------------------------------------------------------------------


class TestRequestIdPropagation:
    def test_x_request_id_is_tolerated_and_does_not_change_outcome(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        with_id = client.post(
            "/extract",
            headers={"X-Request-ID": "req-e2e-001"},
            **valid_pdf_multipart,
        )
        without_id = client.post("/extract", **valid_pdf_multipart)

        assert with_id.status_code == 200
        assert with_id.json() == without_id.json()

    def test_x_request_id_is_not_echoed_in_response_headers_yet(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        response = client.post(
            "/extract",
            headers={"X-Request-ID": "req-e2e-001"},
            **valid_pdf_multipart,
        )

        assert "x-request-id" not in response.headers

    @pytest.mark.xfail(
        reason="TODO: reflejar X-Request-ID en respuesta cuando el "
        "middleware de trazabilidad se implemente",
        strict=True,
    )
    def test_x_request_id_is_echoed_back_once_tracing_is_implemented(
        self, client: TestClient, valid_pdf_multipart: dict[str, Any]
    ) -> None:
        response = client.post(
            "/extract",
            headers={"X-Request-ID": "req-e2e-001"},
            **valid_pdf_multipart,
        )

        assert response.headers.get("x-request-id") == "req-e2e-001"
