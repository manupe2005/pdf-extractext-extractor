"""Fixtures binarias PDF generadas con PyMuPDF (sin binarios externos)."""

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
def heading_pdf() -> bytes:
    """PDF de 1 página con un título grande (24pt) y un cuerpo (11pt)."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Cuerpo normal del documento", fontsize=11)
    page.insert_text((72, 160), "Titulo Principal", fontsize=24)
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def bullet_list_pdf() -> bytes:
    """PDF de 1 página con dos ítems de lista con prefijo de viñeta."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "- Primero", fontsize=11)
    page.insert_text((72, 100), "- Segundo", fontsize=11)
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture()
def two_paragraphs_pdf() -> bytes:
    """PDF de 1 página con dos párrafos separados verticalmente."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Primer parrafo independiente", fontsize=11)
    page.insert_text((72, 400), "Segundo parrafo independiente", fontsize=11)
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
