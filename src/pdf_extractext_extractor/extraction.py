"""Recepción del PDF por multipart/form-data en memoria y POST /extract.

El cuerpo se acota con `MAX_UPLOAD_BYTES` antes de parsear y nunca toca el
disco. Contrato 200: {filename, extracted_text, checksum, content, page_count}
con `extracted_text == content` (mismo string).
"""

import math
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from pdf_extractext_extractor.checksum import compute_sha256
from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import InvalidRequest

from pdf_extractext_extractor.domain.extractor import extract_pdf_data

MULTIPART_CONTENT_TYPE = b"multipart/form-data"

router = APIRouter()


class _InMemoryMultiPartParser(MultiPartParser):
    """Parser con spool infinito: el cuerpo ya viene acotado, nada va a disco."""

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
        # Sin esto Starlette no traduce el multipart corrupto y sería un 500.
        raise InvalidRequest(f"Multipart malformado: {exc}") from exc


@router.post("/extract")
async def extract(request: Request) -> dict[str, Any]:
    """Recibe el PDF, extrae el Markdown y devuelve el contrato de 5 campos."""
    _reject_oversized_declared_body(request)
    form = await _parse_multipart_form(request)

    upload = form.get("file")
    if upload is None:
        raise InvalidRequest("El campo 'file' es obligatorio.")
    if not isinstance(upload, UploadFile):
        raise InvalidRequest("El campo 'file' debe contener un archivo.")
    pdf_bytes = await upload.read()
    filename = upload.filename
    await upload.close()
    if not pdf_bytes:
        raise InvalidRequest("El archivo está vacío.")

    # En threadpool: la extracción es CPU-bound y no debe bloquear el event loop.
    extracted = await run_in_threadpool(extract_pdf_data, pdf_bytes)
    return {
        "filename": filename,
        "extracted_text": extracted.extracted_text,
        "checksum": compute_sha256(pdf_bytes),
        "content": extracted.extracted_text,
        "page_count": extracted.page_count,
    }
