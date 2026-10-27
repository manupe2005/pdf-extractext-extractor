"""Test de concurrencia/admisión: 503 inmediato sin espera."""

import time
import threading

import pytest
from fastapi.testclient import TestClient

from pdf_extractext_extractor.domain.exceptions import InternalProcessingError


class TestEventLoopResponsiveness:
    def test_second_extraction_is_rejected_without_waiting(
        self, client: TestClient, valid_pdf_multipart: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Con MAX_CONCURRENCY=1, la segunda petición concurrente debe
        recibir 503 inmediato con Retry-After, sin bloquear esperando a la
        primera."""

        def _slow(self, _pdf_bytes: bytes):
            time.sleep(2)
            raise InternalProcessingError("simulado")

        # Parchear el extractor concreto usado por el servicio inyectado
        app = getattr(client, "app", None)
        if app is not None and hasattr(app.state, "extraction_service"):
            extractor = app.state.extraction_service._extractor
            monkeypatch.setattr(type(extractor), "extract", _slow)
        else:
            from pdf_extractext_extractor.main import app as main_app

            app = main_app
            extractor = app.state.extraction_service._extractor
            monkeypatch.setattr(type(extractor), "extract", _slow)

        start = time.perf_counter()
        c = TestClient(app)
        results = []

        def do_req():
            results.append(c.post("/extract", **valid_pdf_multipart))

        t1 = threading.Thread(target=do_req)
        t1.start()
        time.sleep(0.3)  # asegurar que t1 adquirió el slot
        r2 = c.post("/extract", **valid_pdf_multipart)
        t1.join(timeout=6)
        elapsed = time.perf_counter() - start

        # r2 debe ser rechazada inmediatamente por admisión
        assert r2.status_code == 503
        assert r2.json()["code"] == "SERVICE_OVERLOADED"
        assert "Retry-After" in r2.headers
        # No debe esperar a los 2s de la primera
        assert elapsed < 2.5
