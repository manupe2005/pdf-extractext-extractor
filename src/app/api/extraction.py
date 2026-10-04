"""Borde público del servicio: POST /extract (multipart/form-data, campo `file`)."""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.domain.models import ExtractionResult
from app.domain.ports import AdmissionLimiter, PDFExtractor
from app.infrastructure.admission_limiter import SemaphoreAdmissionLimiter
from app.infrastructure.pymupdf_extractor import PyMuPDFExtractor

router = APIRouter(tags=["extraction"])


class ExtractionResponse(BaseModel):
    """Contrato C1 extendido devuelto al API Service."""

    model_config = ConfigDict(from_attributes=True)

    filename: str
    extracted_text: str
    checksum: str
    content: str
    page_count: int


def get_pdf_extractor() -> PDFExtractor:
    return PyMuPDFExtractor()


_admission_limiter = SemaphoreAdmissionLimiter(
    slots=settings.admission_slots,
    timeout_seconds=settings.admission_timeout_seconds,
)


def get_admission_limiter() -> AdmissionLimiter:
    """Singleton por proceso: el semáforo de admisión debe compartirse."""
    return _admission_limiter


@router.post("/extract")
async def extract_pdf(
    file: Annotated[UploadFile, File()],
    extractor: Annotated[PDFExtractor, Depends(get_pdf_extractor)],
    limiter: Annotated[AdmissionLimiter, Depends(get_admission_limiter)],
) -> ExtractionResponse:
    data = await file.read()
    checksum = hashlib.sha256(data).hexdigest()
    async with limiter:
        extracted_text, page_count = extractor.extract(data)
    result = ExtractionResult(
        filename=file.filename or "",
        extracted_text=extracted_text,
        checksum=checksum,
        content=extracted_text,
        page_count=page_count,
    )
    return ExtractionResponse.model_validate(result)
