"""Fixtures compartidas de la suite.

`valid_pdf_multipart` es la carga multipart reutilizable para el endpoint
POST /extract, pensada para compartirse con las pruebas del cliente de la
API: `client.post("/extract", **valid_pdf_multipart)`.
"""

from typing import Any

import pytest

PDF_FILENAME = "informe cabras final.pdf"


def _build_minimal_pdf() -> bytes:
    """PDF mínimo válido de una página con una línea de texto."""
    stream = b"BT /F1 12 Tf 10 50 Td (Proyecto cabras) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_position = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        pdf += b"%010d 00000 n \n" % offset
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_position,
    )
    return bytes(pdf)


PDF_BYTES = _build_minimal_pdf()


@pytest.fixture()
def valid_pdf_multipart() -> dict[str, Any]:
    """Multipart válido listo para POST /extract con httpx/TestClient.

    Uso: `client.post("/extract", **valid_pdf_multipart)`
    """
    return {"files": {"file": (PDF_FILENAME, PDF_BYTES, "application/pdf")}}
