"""Extracción de PDF a Markdown con PyMuPDF, solo con layout (sin OCR).

Errores: PDF no procesable -> InvalidPDFContentError (422);
fallo de la librería -> InternalProcessingError (500).
"""

import logging
from dataclasses import dataclass

import pymupdf

from pdf_extractext_extractor.domain.exceptions import (
    InternalProcessingError,
    InvalidPDFContentError,
)

logger = logging.getLogger(__name__)

_PAGE_SEPARATOR = "\n\n---\n\n"
_BULLET_PREFIXES = ("•", "-", "*", "·", "‣", "▪", "◦")
_BOLD_FLAG = 1 << 4


@dataclass(frozen=True)
class ExtractedPDFData:
    """Resultado de la extracción de un PDF."""

    extracted_text: str
    page_count: int


def extract_pdf_data(pdf_bytes: bytes) -> ExtractedPDFData:
    """Extrae todas las páginas a Markdown y devuelve su page_count."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.needs_pass:
                raise InvalidPDFContentError("El PDF está protegido con contraseña")
            pages = (_page_to_markdown(page) for page in document)
            markdown = _PAGE_SEPARATOR.join(page for page in pages if page)
            return ExtractedPDFData(
                extracted_text=markdown,
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


def _page_to_markdown(page: "pymupdf.Page") -> str:
    """Convierte el contenido textual de una página en un bloque Markdown."""
    # Sin TEXT_PRESERVE_IMAGES: los bloques de imagen se descartan igual.
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    blocks = page.get_text("dict", flags=flags)["blocks"]
    base_size = _base_font_size(blocks)
    paragraph_gap = base_size if base_size > 0 else 12.0
    elements: list[str] = []
    paragraph: list[str] = []
    previous_bottom: float | None = None

    def flush_paragraph() -> None:
        if paragraph:
            elements.append(" ".join(paragraph))
            paragraph.clear()

    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text, size, bold = _line_properties(line)
            stripped = text.strip()
            if not stripped:
                continue

            bbox = line.get("bbox")
            top = float(bbox[1]) if bbox else None
            bottom = float(bbox[3]) if bbox else None

            # Un salto vertical mayor al alto de línea indica nuevo párrafo.
            if (
                paragraph
                and previous_bottom is not None
                and top is not None
                and top - previous_bottom > paragraph_gap
            ):
                flush_paragraph()

            bullet = _bullet_content(stripped)
            if bullet is not None:
                flush_paragraph()
                elements.append(f"- {bullet}")
            else:
                level = _heading_level(
                    size, base_size, bold, len(stripped.split())
                )
                if level:
                    flush_paragraph()
                    elements.append(f"{'#' * level} {stripped}")
                else:
                    paragraph.append(stripped)

            previous_bottom = bottom

    flush_paragraph()
    return "\n\n".join(elements)


def _line_properties(line: dict) -> tuple[str, float, bool]:
    """Devuelve el texto de la línea, su tamaño máximo y si es toda negrita."""
    parts: list[str] = []
    max_size = 0.0
    bold_chars = 0
    total_chars = 0

    for span in line.get("spans", []):
        text = span.get("text", "")
        parts.append(text)
        length = len(text.strip())
        total_chars += length
        max_size = max(max_size, float(span.get("size", 0.0)))
        if int(span.get("flags", 0)) & _BOLD_FLAG:
            bold_chars += length

    bold = total_chars > 0 and bold_chars >= total_chars
    return "".join(parts), max_size, bold


def _base_font_size(blocks: list[dict]) -> float:
    """Tamaño de fuente dominante de la página, ponderado por caracteres."""
    weights: dict[float, int] = {}
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                length = len(span.get("text", "").strip())
                if length:
                    size = round(float(span.get("size", 0.0)), 1)
                    weights[size] = weights.get(size, 0) + length
    if not weights:
        return 0.0
    return max(weights, key=lambda size: (weights[size], -size))


def _heading_level(
    size: float, base_size: float, bold: bool, word_count: int
) -> int:
    """Nivel de encabezado (#, ##, ###) según jerarquía de tamaño o negrita."""
    if base_size <= 0 or size <= 0:
        return 0
    ratio = size / base_size
    if ratio >= 1.8:
        return 1
    if ratio >= 1.5:
        return 2
    if ratio >= 1.25:
        return 3
    if bold and ratio >= 1.05 and word_count <= 12:
        return 3
    return 0


def _bullet_content(text: str) -> str | None:
    """Contenido sin el prefijo si la línea es un ítem de lista; si no, None."""
    for prefix in _BULLET_PREFIXES:
        if text.startswith(prefix):
            content = text[len(prefix):].lstrip(" .\t")
            if content:
                return content
    return None
