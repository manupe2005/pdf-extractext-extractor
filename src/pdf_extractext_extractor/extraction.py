"""Recepción del PDF por multipart/form-data: POST /extract (Issue #2).

El archivo llega en el campo `file`, se valida estructuralmente y se retiene
100% en memoria, sin tocar el disco. El equivalente óptimo al `UploadFile`
declarativo es leer el stream acotado por el límite defensivo y parsear con
un parser multipart de spool infinito: la vía declarativa volcaría a disco
los archivos de más de 1 MB (SpooledTemporaryFile) y no permite acotar el
cuerpo antes de leerlo.

Contrato final (Issue #5, C1 + TP):

    200 -> {filename, extracted_text, checksum, content, page_count}
           Regla estricta: extracted_text == content (mismo string).
    400 -> {"code": "INVALID_REQUEST", "message": "<detalle>"}
    422/500: traducidos desde el dominio por los handlers de main.py.
"""

import math
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from pdf_extractext_extractor.checksum import compute_sha256
from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import InvalidRequest

from pdf_extractext_extractor.domain.extractor import extract_pdf_data

MULTIPART_CONTENT_TYPE = b"multipart/form-data"

router = APIRouter()


class _InMemoryMultiPartParser(MultiPartParser):
    """Parser multipart con retención garantizada 100% en memoria.

    Starlette vuelca los archivos a disco en cuanto superan 1 MB; aquí el
    spool nunca rueda porque el cuerpo ya quedó acotado por el límite
    defensivo antes de empezar a parsear.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.spool_max_size = math.inf


def _reject_oversized_declared_body(request: Request) -> None:
    """Falla rápido si el Content-Length declarado ya supera el límite."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise InvalidRequest(f"El cuerpo excede el límite de {settings.max_upload_bytes} bytes.")


async def _bounded_stream(
    stream: AsyncGenerator[bytes, None], limit: int
) -> AsyncGenerator[bytes, None]:
    """Envoltorio del stream de entrada que aborta al superar `limit` bytes."""
    accumulated = 0
    async for chunk in stream:
        accumulated += len(chunk)
        if accumulated > limit:
            raise InvalidRequest(f"El cuerpo excede el límite de {limit} bytes.")
        yield chunk


async def _parse_multipart_form(request: Request) -> FormData:
    """Parsea el cuerpo multipart en memoria o falla con 400 estructural."""
    content_type, params = parse_options_header(request.headers.get("content-type", ""))
    if content_type != MULTIPART_CONTENT_TYPE:
        raise InvalidRequest("El Content-Type debe ser multipart/form-data.")
    if not params.get(b"boundary"):
        raise InvalidRequest("Falta el boundary del multipart.")

    parser = _InMemoryMultiPartParser(
        request.headers,
        _bounded_stream(request.stream(), settings.max_upload_bytes),
    )
    try:
        return await parser.parse()
    except (MultiPartException, MultipartParseError) as exc:
        # MultiPartException: límites del parser (demasiados campos, partes
        # gigantes, Content-Disposition sin name). MultipartParseError: cuerpo
        # corrupto; Starlette no la traduce, sin esto sería un 500.
        raise InvalidRequest(f"Multipart malformado: {exc}") from exc


@router.post("/extract")
async def extract(request: Request) -> dict[str, Any]:
    """Orquesta recepción -> extracción de texto -> checksum (C1 + TP).

    Devuelve el contrato combinado con exactamente cinco campos; los errores
    del dominio (InvalidPDFContentError / InternalProcessingError) se traducen
    en los exception handlers registrados en main.py.
    """
    _reject_oversized_declared_body(request)
    form = await _parse_multipart_form(request)

    upload = form.get("file")
    if upload is None:
        raise InvalidRequest("El campo 'file' es obligatorio.")
    if not isinstance(upload, UploadFile):
        raise InvalidRequest("El campo 'file' debe contener un archivo.")
    pdf_bytes = await upload.read()
    if not pdf_bytes:
        raise InvalidRequest("El archivo está vacío.")

    extracted = extract_pdf_data(pdf_bytes)
    return {
        "filename": upload.filename,
        "extracted_text": extracted.extracted_text,
        "checksum": compute_sha256(pdf_bytes),
        "content": extracted.extracted_text,
        "page_count": extracted.page_count,
    }
