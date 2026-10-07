"""Issue #10: Contrato E2E que la API Service consume de Extraction.

Estos tests ejercitan la app exactamente como la API lo hará a través de
Traefik interno: POST /extract con multipart/form-data, header X-Request-ID
opcional, y assertions sobre el contrato extendido de respuesta:

    200 -> {filename, extracted_text, checksum, content, page_count}
    400 -> {code: "INVALID_REQUEST", message}
    422 -> {code: "INVALID_PDF_CONTENT", message}
    500 -> {code: "INTERNAL_ERROR", message}
    503 -> {code: "INTERNAL_ERROR", message} + Retry-After (admisión satura)

Propagación de X-Request-ID: la app actualmente NO refleja el header; se
asserts que lo tolera y se deja marcado xfail el reflejo futuro en
respuesta/logs.

Uso de fixtures: `valid_pdf_multipart` (tests/conftest.py) arma un
multipart válido con un PDF mínimo de 1 página cuyo texto incluye
"Proyecto cabras".
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

EXTRACTOR_PATCH_TARGET = "pdf_extractext_extractor.extraction.extract_pdf_data"
EXPECTED_SUCCESS_KEYS = {
    "filename",
    "extracted_text",
    "checksum",
    "content",
    "page_count",
}
ERROR_ENVELOPE_KEYS = {"code", "message"}


@pytest.fixture()
def client() -> TestClient:
    """Cliente HTTP de la app completa, idéntico al que usaría tests/api/."""
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
        assert set(payload) == ERROR_ENVELOPE_KEYS
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
        assert set(payload) == ERROR_ENVELOPE_KEYS
        assert payload["code"] == "INVALID_PDF_CONTENT"

    def test_domain_invalid_pdf_error_maps_to_422(
        self,
        client: TestClient,
        valid_pdf_multipart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_invalid(_pdf_bytes: bytes) -> None:
            raise InvalidPDFContentError("El contenido recibido no es un PDF válido")

        monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _raise_invalid)

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 422
        assert response.json() == {
            "code": "INVALID_PDF_CONTENT",
            "message": "El contenido recibido no es un PDF válido",
        }

    def test_internal_processing_error_maps_to_500(
        self,
        client: TestClient,
        valid_pdf_multipart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_internal(_pdf_bytes: bytes) -> None:
            raise InternalProcessingError("Fallo inesperado procesando el PDF")

        monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _raise_internal)

        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 500
        assert response.json() == {
            "code": "INTERNAL_ERROR",
            "message": "Fallo inesperado procesando el PDF",
        }

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
                "code": "INTERNAL_ERROR",
                "message": "Servicio saturado. Reintente más tarde.",
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
