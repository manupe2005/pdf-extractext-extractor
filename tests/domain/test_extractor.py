"""FASE ROJA (Issue #4): extracción de texto PDF con PyMuPDF.

Estos tests están diseñados para fallar catastróficamente:
los módulos `app.domain.extractor` y `app.domain.exceptions` aún no existen,
por lo que la colección fallará con ModuleNotFoundError.
"""

import pytest

from app.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)
from app.domain.extractor import extract_pdf_data


# ---------------------------------------------------------------------------
# Escenario 1: PDF válido con texto -> extrae contenido y page_count
# ---------------------------------------------------------------------------


class TestValidPdfExtraction:
    def test_extracts_full_text_from_all_pages(
        self, multi_page_text_pdf: bytes
    ) -> None:
        result = extract_pdf_data(multi_page_text_pdf)

        assert "Contenido de la página 1" in result.extracted_text
        assert "Contenido de la página 2" in result.extracted_text
        assert "Contenido de la página 3" in result.extracted_text

    def test_returns_total_page_count(self, multi_page_text_pdf: bytes) -> None:
        result = extract_pdf_data(multi_page_text_pdf)

        assert result.page_count == 3


# ---------------------------------------------------------------------------
# Escenario 2: PDF corrupto -> InvalidPDFContentError (mapeable a 422)
# ---------------------------------------------------------------------------


class TestCorruptedPdf:
    def test_raises_invalid_pdf_content_error(
        self, corrupted_pdf: bytes
    ) -> None:
        with pytest.raises(InvalidPDFContentError):
            extract_pdf_data(corrupted_pdf)

    def test_non_pdf_binary_payload_is_rejected(
        self, not_a_pdf_binary: bytes
    ) -> None:
        with pytest.raises(InvalidPDFContentError):
            extract_pdf_data(not_a_pdf_binary)

    def test_error_is_not_internal_processing(
        self, corrupted_pdf: bytes
    ) -> None:
        # Contrato: el mismo input corrupto jamás debe propagarse como 500
        with pytest.raises(InvalidPDFContentError) as exc_info:
            extract_pdf_data(corrupted_pdf)

        assert not isinstance(exc_info.value, InternalProcessingError)


# ---------------------------------------------------------------------------
# Escenario 3: fallo inesperado de PyMuPDF -> InternalProcessingError (500)
# ---------------------------------------------------------------------------


class TestUnexpectedLibraryFailure:
    def test_raises_internal_processing_error(
        self,
        structurally_valid_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _explode(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("fallo desconocido en el motor de render")

        # En Fase Verde el dominio abrirá el PDF vía pymupdf.open();
        # forzamos un crash no relacionado con el formato del documento.
        monkeypatch.setattr("app.domain.extractor.pymupdf.open", _explode)

        with pytest.raises(InternalProcessingError):
            extract_pdf_data(structurally_valid_pdf)

    def test_chains_original_exception(
        self,
        structurally_valid_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original = RuntimeError("desbordamiento interno")
        monkeypatch.setattr(
            "app.domain.extractor.pymupdf.open",
            lambda *_a, **_k: (_ for _ in ()).throw(original),
        )

        with pytest.raises(InternalProcessingError) as exc_info:
            extract_pdf_data(structurally_valid_pdf)

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# Escenario 4: PDF válido sin texto extraíble (solo imágenes) -> ""
# ---------------------------------------------------------------------------


class TestImageOnlyPdf:
    def test_returns_empty_string_without_errors(
        self, image_only_pdf: bytes
    ) -> None:
        result = extract_pdf_data(image_only_pdf)

        assert result.extracted_text == ""

    def test_page_count_still_reported(self, image_only_pdf: bytes) -> None:
        result = extract_pdf_data(image_only_pdf)

        assert result.page_count == 2
