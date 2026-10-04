"""Recepción del PDF por multipart/form-data: POST /extract (Issue #2).

El archivo llega en el campo `file`, se valida estructuralmente y se retiene
100% en memoria, sin tocar el disco. El equivalente óptimo al `UploadFile`
declarativo es leer el stream acotado por el límite defensivo y parsear con
un parser multipart de spool infinito: la vía declarativa volcaría a disco
los archivos de más de 1 MB (SpooledTemporaryFile) y no permite acotar el
cuerpo antes de leerlo.

Contrato de esta fase (recepción):

    200 -> {"filename": <str>, "size": <int>}
    400 -> {"code": "INVALID_REQUEST", "message": "<detalle>"}
"""

import math
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import InvalidRequest

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
    """Recibe el PDF del campo `file` y acusa la recepción en memoria.

    Devuelve el filename íntegro de la cabecera multipart y el tamaño de los
    bytes recibidos; la extracción de texto y el checksum se agregan en issues
    posteriores sobre esta misma ruta.
    """
    _reject_oversized_declared_body(request)
    form = await _parse_multipart_form(request)

    upload = form.get("file")
    if upload is None:
        raise InvalidRequest("El campo 'file' es obligatorio.")
    if not isinstance(upload, UploadFile):
        raise InvalidRequest("El campo 'file' debe contener un archivo.")
    content = await upload.read()
    if not content:
        raise InvalidRequest("El archivo está vacío.")

    return {"filename": upload.filename, "size": len(content)}
