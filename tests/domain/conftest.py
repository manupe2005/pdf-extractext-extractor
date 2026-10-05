"""Fixtures binarias PDF para las pruebas del dominio de extracción.

Los PDFs se generan programáticamente con PyMuPDF (la misma librería bajo
test), garantizando archivos estructuralmente válidos sin depender de
binarios externos versionados.
"""

import pymupdf
import pytest


@pytest.fixture()
def multi_page_text_pdf() -> bytes:
    """PDF de 3 páginas con texto "Contenido de la página N"."""
    document = pymupdf.open()
    for number in (1, 2, 3):
        page = document.new_page()
        page.insert_text((72, 72), f"Contenido de la página {number}")
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def structurally_valid_pdf() -> bytes:
    """PDF mínimo válido de 1 página (usado para el test con monkeypatch)."""
    document = pymupdf.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def image_only_pdf() -> bytes:
    """PDF válido de 2 páginas con imágenes, sin capa de texto extraíble."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10))
    image_bytes = pixmap.tobytes("png")
    document = pymupdf.open()
    for _ in range(2):
        page = document.new_page(width=200, height=200)
        page.insert_image(pymupdf.Rect(0, 0, 100, 100), stream=image_bytes)
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def corrupted_pdf() -> bytes:
    """Cabecera PDF + cuerpo binario truncado (no procesable)."""
    return b"%PDF-1.4\n" + b"\x00\xff\xde\xad\x03\x04obj roto" * 16


@pytest.fixture()
def not_a_pdf_binary() -> bytes:
    """Bytes aleatorios sin cabecera PDF."""
    return bytes(range(256)) * 4
