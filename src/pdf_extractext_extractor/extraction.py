"""Recepción multipart 100% en memoria: POST /extract.

Contrato: 200 con {filename, extracted_text, checksum, content, page_count}
(donde extracted_text == content). 400 con {"code":"INVALID_REQUEST","message":"..."}
para fallos estructurales; 422/500 desde el dominio vía exception handlers.
"""

import math
from collections.abc import AsyncGenerator, Mapping
from typing import Any

from fastapi import APIRouter, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from pdf_extractext_extractor.config import settings
from pdf_extractext_extractor.errors import InvalidRequest
from pdf_extractext_extractor.ports.interfaces import ChecksumCalculator, PDFExtractor

# Re-exports para mantener compatibilidad con tests que puedan importar desde aquí
from pdf_extractext_extractor.checksum import compute_sha256  # noqa: F401
from pdf_extractext_extractor.domain.extractor import extract_pdf_data  # noqa: F401

MULTIPART_CONTENT_TYPE = b"multipart/form-data"

router = APIRouter()


class ExtractionService:
    """Servicio de aplicación que orquesta extracción y checksum."""

    def __init__(self, extractor: PDFExtractor, checksum_calculator: ChecksumCalculator) -> None:
        self._extractor = extractor
        self._checksum_calculator = checksum_calculator

    def extract(self, pdf_bytes: bytes, filename: str | None) -> dict[str, Any]:
        extracted = self._extractor.extract(pdf_bytes)
        return {
            "filename": filename,
            "extracted_text": extracted.extracted_text,
            "checksum": self._checksum_calculator.calculate(pdf_bytes),
            "content": extracted.extracted_text,
            "page_count": extracted.page_count,
        }


class _InMemoryMultiPartParser(MultiPartParser):
    """Parser multipart que nunca utiliza disco para spooling."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Forzar spool infinito: evita SpooledTemporaryFile.rollover() a disco
        self.spool_max_size = math.inf


def _validate_multipart_headers(headers: Mapping[str, str]) -> None:
    """Valida Content-Type multipart/form-data y extrae boundary."""
    content_type, params = parse_options_header(headers.get("content-type", ""))
    if content_type != MULTIPART_CONTENT_TYPE:
        raise InvalidRequest("El Content-Type debe ser multipart/form-data.")
    boundary = params.get(b"boundary")
    if not boundary:
        raise InvalidRequest("Falta el boundary del multipart.")


def _get_required_file(form: FormData) -> UploadFile:
    """Extrae y valida el campo 'file' del FormData."""
    upload = form.get("file")
    if upload is None:
        raise InvalidRequest("El campo 'file' es obligatorio.")
    if not isinstance(upload, UploadFile):
        raise InvalidRequest("El campo 'file' debe contener un archivo.")
    return upload


async def _read_non_empty_file(upload: UploadFile) -> bytes:
    """Lee el archivo y garantiza que no esté vacío."""
    pdf_bytes = await upload.read()
    if not pdf_bytes:
        raise InvalidRequest("El archivo está vacío.")
    return pdf_bytes


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


async def _limited_request_stream(request: Request) -> AsyncGenerator[bytes, None]:
    """Aplica defensa de tamaño unificada: Content-Length + conteo por stream."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        if int(declared) > settings.max_upload_bytes:
            raise InvalidRequest(f"El cuerpo excede el límite de {settings.max_upload_bytes} bytes.")
    async for chunk in _bounded_stream(request.stream(), settings.max_upload_bytes):
        yield chunk


async def _parse_multipart_form(request: Request) -> FormData:
    """Parsea el cuerpo multipart 100% en memoria o falla con 400 estructural."""
    _validate_multipart_headers(request.headers)
    parser = _InMemoryMultiPartParser(
        request.headers,
        _limited_request_stream(request),
    )
    try:
        return await parser.parse()
    except (MultiPartException, MultipartParseError) as exc:
        raise InvalidRequest(f"Multipart malformado: {exc}") from exc


def get_extraction_service(request: Request) -> ExtractionService:
    service = getattr(request.app.state, "extraction_service", None)
    if service is None:
        raise RuntimeError("ExtractionService no inicializado en app.state")
    return service


@router.post("/extract")
async def extract(request: Request) -> dict[str, Any]:
    """Orquesta recepción -> extracción de texto -> checksum."""
    service = get_extraction_service(request)
    form = await _parse_multipart_form(request)
    upload = _get_required_file(form)
    pdf_bytes = await _read_non_empty_file(upload)
    return service.extract(pdf_bytes, upload.filename)
