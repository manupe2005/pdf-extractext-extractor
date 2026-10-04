"""Modelos de dominio del Extraction Service (libres de frameworks)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Resultado del flujo de extracción (contrato C1 extendido)."""

    filename: str
    extracted_text: str
    checksum: str
    content: str
    page_count: int
