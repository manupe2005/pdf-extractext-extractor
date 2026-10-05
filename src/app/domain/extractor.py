"""Extracción de texto de PDFs con PyMuPDF.

Contrato del dominio:
- PDF válido: retorna ExtractedPDFData con el texto completo y page_count.
- PDF corrupto / no procesable: InvalidPDFContentError (-> 422).
- Fallo inesperado de la librería: InternalProcessingError (-> 500).
- PDF válido sin texto extraíble: ExtractedPDFData con extracted_text == "".
"""

import logging
from dataclasses import dataclass

import pymupdf

from app.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedPDFData:
    """Resultado de la extracción de un PDF."""

    extracted_text: str
    page_count: int


def extract_pdf_data(pdf_bytes: bytes) -> ExtractedPDFData:
    """Extrae el texto completo de todas las páginas de un PDF en memoria."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            text = "".join(page.get_text() for page in document)
            return ExtractedPDFData(
                extracted_text=text,
                page_count=document.page_count,
            )
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
        raise InvalidPDFContentError(
            "El contenido recibido no es un PDF válido o procesable"
        ) from error
    except InvalidPDFContentError:
        raise
    except Exception as error:
        logger.exception("Fallo inesperado extrayendo texto del PDF")
        raise InternalProcessingError(
            "Fallo inesperado procesando el PDF"
        ) from error
