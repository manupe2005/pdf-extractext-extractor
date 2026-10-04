"""Adapter de PDFExtractor sobre PyMuPDF."""

import pymupdf

from app.domain.errors import InvalidPDFFormatError


class PyMuPDFExtractor:
    """Extracción en memoria, cero escrituras a disco."""

    def extract(self, data: bytes) -> tuple[str, int]:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                page_count = document.page_count
                extracted_text = "".join(page.get_text() for page in document)
        except pymupdf.FileDataError as exc:
            raise InvalidPDFFormatError(
                "El archivo recibido no es un PDF válido o está corrupto."
            ) from exc
        return extracted_text, page_count
