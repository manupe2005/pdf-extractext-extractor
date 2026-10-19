"""La extracción corre en threadpool: el event loop atiende mientras trabaja."""

import asyncio
import threading
import time

import httpx
import pytest

from pdf_extractext_extractor.domain.extractor import ExtractedPDFData
from pdf_extractext_extractor.main import create_app

EXTRACTOR_PATCH_TARGET = "pdf_extractext_extractor.extraction.extract_pdf_data"

SLOW_SECONDS = 1.5
RESPONSIVE_LIMIT = 0.75


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
    )


@pytest.fixture()
def slow_extraction(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Extrae con retardo y expone un Event que se activa al terminar."""
    finished = threading.Event()

    def _slow(_pdf_bytes: bytes) -> ExtractedPDFData:
        time.sleep(SLOW_SECONDS)
        finished.set()
        return ExtractedPDFData(extracted_text="ok", page_count=1)

    monkeypatch.setattr(EXTRACTOR_PATCH_TARGET, _slow)
    return finished


class TestEventLoopResponsiveness:
    def test_health_answers_while_extraction_runs(
        self, slow_extraction: threading.Event, valid_pdf_multipart: dict
    ) -> None:
        async def scenario() -> None:
            async with _client() as client:
                extraction = asyncio.create_task(
                    client.post("/extract", **valid_pdf_multipart)
                )
                await asyncio.sleep(0.05)
                start = time.perf_counter()
                health = await client.get("/health")
                latency = time.perf_counter() - start
                answered_during_extraction = not slow_extraction.is_set()
                extraction_response = await extraction

            assert extraction_response.status_code == 200
            assert health.status_code == 200
            assert latency < RESPONSIVE_LIMIT
            assert answered_during_extraction, "/health esperó a la extracción"

        asyncio.run(scenario())

    def test_second_extraction_is_rejected_without_waiting(
        self, slow_extraction: threading.Event, valid_pdf_multipart: dict
    ) -> None:
        async def scenario() -> None:
            async with _client() as client:
                first = asyncio.create_task(
                    client.post("/extract", **valid_pdf_multipart)
                )
                await asyncio.sleep(0.05)
                start = time.perf_counter()
                second = await client.post("/extract", **valid_pdf_multipart)
                waited = time.perf_counter() - start
                rejected_during_extraction = not slow_extraction.is_set()
                first_response = await first

            assert first_response.status_code == 200
            assert second.status_code == 503
            assert second.json()["code"] == "SERVICE_OVERLOADED"
            assert second.headers["retry-after"]
            assert waited < RESPONSIVE_LIMIT
            assert rejected_during_extraction, "el 503 esperó a la extracción"

        asyncio.run(scenario())
