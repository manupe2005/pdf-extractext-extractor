"""FASE ROJA -> VERDE (Issue #5): POST /extract, contrato combinado C1 + TP.

Contrato combinado de respuesta 200:
    {filename, extracted_text, checksum, content, page_count}
    Regla estricta: extracted_text == content (mismo string exacto).

Envelope de error estricto {code, message}:
    400 INVALID_REQUEST      -> multipart ausente / malformado / vacío
    422 INVALID_PDF_CONTENT  -> InvalidPDFContentError del dominio
    500 INTERNAL_ERROR       -> InternalProcessingError del dominio

Nota de módulos: el paquete de producción es el plano
`pdf_extractext_extractor`; el dominio de extracción vive en
`app.domain`. Los monkeypatch apuntan al símbolo importado a nivel de
módulo en `pdf_extractext_extractor.extraction`.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)

EXPECTED_SUCCESS_KEYS = {
    "filename",
    "extracted_text",
    "checksum",
    "content",
    "page_count",
}

EXTRACTOR_PATCH_TARGET = "pdf_extractext_extractor.extraction.extract_pdf_data"


# ---------------------------------------------------------------------------
# Caso 200: contrato combinado C1 + TP
# ---------------------------------------------------------------------------


class TestExtractSuccessContract:
    def test_returns_exactly_the_five_contract_fields(
        self, client: TestClient, valid_pdf_multipart: dict
    ) -> None:
        response = client.post("/extract", **valid_pdf_multipart)

        assert response.status_code == 200
        assert set(response.json()) == EXPECTED_SUCCESS_KEYS

    def test_extracted_text_and_content_are_identical_strings(
        self, client: TestClient, valid_pdf_multipart: dict
    ) -> None:
        payload = client.post("/extract", **valid_pdf_multipart).json()

        assert payload["extracted_text"] == payload["content"]
        assert "Proyecto cabras" in payload["content"]

    def test_reports_filename_verbatim(
        self, client: TestClient, valid_pdf_multipart: dict
    ) -> None:
        payload = client.post("/extract", **valid_pdf_multipart).json()

        assert payload["filename"] == "informe cabras final.pdf"

    def test_computes_sha256_checksum_of_the_pdf_bytes(
        self, client: TestClient, valid_pdf_multipart: dict, pdf_bytes: bytes
    ) -> None:
        payload = client.post("/extract", **valid_pdf_multipart).json()

        assert payload["checksum"] == hashlib.sha256(pdf_bytes).hexdigest()

    def test_reports_page_count_of_the_pdf(
        self, client: TestClient, valid_pdf_multipart: dict
    ) -> None:
        payload = client.post("/extract", **valid_pdf_multipart).json()

        assert payload["page_count"] == 1


# ---------------------------------------------------------------------------
# Caso 400: INVALID_REQUEST — multipart ausente / vacío
# ---------------------------------------------------------------------------


class TestExtractInvalidRequest:
    def test_missing_file_field_returns_400_with_envelope(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/extract",
            files={"not_the_file_field": ("x.pdf", b"%PDF-x", "application/pdf")},
        )

        assert response.status_code == 400
        payload = response.json()
        assert payload["code"] == "INVALID_REQUEST"
        assert isinstance(payload["message"], str)

    def test_request_without_multipart_content_type_returns_400(
        self, client: TestClient
    ) -> None:
        response = client.post("/extract", content=b"%PDF-1.4 raw body")

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"

    def test_empty_file_field_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/extract",
            files={"file": ("vacio.pdf", b"", "application/pdf")},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"

    def test_error_envelope_has_exactly_code_and_message_keys(
        self, client: TestClient
    ) -> None:
        payload = client.post("/extract", content=b"sin multipart").json()

        assert set(payload) == {"code", "message"}
        assert all(isinstance(value, str) for value in payload.values())


# ---------------------------------------------------------------------------
# Caso 422: INVALID_PDF_CONTENT — traducción de InvalidPDFContentError
# ---------------------------------------------------------------------------


class TestExtractInvalidPdfContent:
    def test_domain_error_maps_to_422_with_envelope(
        self,
        client: TestClient,
        valid_pdf_multipart: dict,
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


# ---------------------------------------------------------------------------
# Caso 500: INTERNAL_ERROR — traducción de InternalProcessingError
# ---------------------------------------------------------------------------


class TestExtractInternalError:
    def test_domain_error_maps_to_500_with_envelope(
        self,
        client: TestClient,
        valid_pdf_multipart: dict,
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


# ---------------------------------------------------------------------------
# Garantías negativas del catálogo: jamás emitir 415, 404 ni 409
# ---------------------------------------------------------------------------


class TestForbiddenStatusCodes:
    @pytest.mark.parametrize("forbidden_status", [409, 404, 415])
    def test_error_paths_never_leak_forbidden_status_codes(
        self,
        client: TestClient,
        valid_pdf_multipart: dict,
        monkeypatch: pytest.MonkeyPatch,
        forbidden_status: int,
    ) -> None:
        def _raise_domain(_pdf_bytes: bytes) -> None:
            raise InvalidPDFContentError("PDF inválido")

        monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _raise_domain)

        for response in (
            client.post("/extract", content=b"sin multipart"),
            client.post("/extract", **valid_pdf_multipart),
        ):
            assert response.status_code != forbidden_status
