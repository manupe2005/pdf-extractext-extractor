"""Contratos (Ports) para invertir dependencias entre capas.

Estos Protocols permiten desacoplar la capa de aplicación de las
implementaciones concretas (PyMuPDF, hashlib), cumpliendo con el principio
de Inversión de Dependencias (DIP).
"""

from typing import Protocol

from pdf_extractext_extractor.domain.extractor import ExtractedPDFData


class PDFExtractor(Protocol):
    """Puerto para la extracción de texto desde un PDF."""

    def extract(self, pdf_bytes: bytes) -> ExtractedPDFData:
        """Extrae texto y metadatos de un PDF a partir de sus bytes."""
        ...


class ChecksumCalculator(Protocol):
    """Puerto para el cálculo de checksums sobre bytes."""

    def calculate(self, data: bytes) -> str:
        """Calcula el checksum del contenido y lo retorna en formato hexadecimal."""
        ...
