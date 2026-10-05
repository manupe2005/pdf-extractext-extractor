"""FASE ROJA -> VERDE (Issue #6): control de admisión con backpressure.

Contrato:
    503 -> {"code": "INTERNAL_ERROR", "message": "<detalle>"} + Retry-After
           Solo cuando no hay capacidad de admisión; el rechazo es inmediato.
    422 -> un PDF inválido que logra admisión SIGUE siendo 422 bajo carga.

El semáforo es por proceso y la adquisición es no bloqueante: si no hay
slot libre no se espera, se rechaza de inmediato (cero acumulación).
"""

import asyncio
import json

from fastapi.testclient import TestClient
from starlette.requests import Request

from pdf_extractext_extractor.admission import AdmissionMiddleware
from pdf_extractext_extractor.main import create_app


def _request_for(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _never_called(request: Request):  # pragma: no cover
    raise AssertionError("el downstream no debe ejecutarse sin admisión")


class TestAdmissionRejection:
    def test_saturated_returns_503_with_contract_envelope(self) -> None:
        async def scenario() -> None:
            middleware = AdmissionMiddleware(
                _never_called, max_concurrency=1, retry_after=3
            )
            await middleware.semaphore.acquire()  # satura el único slot

            response = await middleware.dispatch(
                _request_for("/extract"), _never_called
            )

            assert response.status_code == 503
            assert json.loads(response.body) == {
                "code": "INTERNAL_ERROR",
                "message": response_body_message(json.loads(response.body)),
            }
            assert set(json.loads(response.body)) == {"code", "message"}
            assert json.loads(response.body)["code"] == "INTERNAL_ERROR"

        asyncio.run(scenario())

    def test_saturated_response_includes_retry_after_header(self) -> None:
        async def scenario() -> None:
            middleware = AdmissionMiddleware(
                _never_called, max_concurrency=1, retry_after=3
            )
            await middleware.semaphore.acquire()

            response = await middleware.dispatch(
                _request_for("/extract"), _never_called
            )

            assert response.headers["retry-after"] == "3"

        asyncio.run(scenario())

    def test_rejection_is_immediate_without_waiting(self) -> None:
        """Si no hay slot, no se espera al semáforo: la respuesta sale ya."""

        async def scenario() -> None:
            middleware = AdmissionMiddleware(
                _never_called, max_concurrency=1, retry_after=1
            )
            await middleware.semaphore.acquire()

            # Si dispatch esperara al semáforo, este timeout estallaría.
            response = await asyncio.wait_for(
                middleware.dispatch(_request_for("/extract"), _never_called),
                timeout=0.5,
            )
            assert response.status_code == 503
            assert middleware.rejections == 1

        asyncio.run(scenario())

    def test_health_bypasses_admission(self) -> None:
        """Liveness nunca se ahoga: /health no consume slots del semáforo."""

        async def downstream(request: Request):
            from starlette.responses import JSONResponse

            return JSONResponse({"status": "ok"})

        async def scenario() -> None:
            middleware = AdmissionMiddleware(
                downstream, max_concurrency=1, retry_after=1
            )
            await middleware.semaphore.acquire()  # saturado

            response = await middleware.dispatch(_request_for("/health"), downstream)
            assert response.status_code == 200

        asyncio.run(scenario())


class TestAdmissionPreservesDomainErrors:
    def test_corrupt_pdf_still_returns_422_when_admitted(
        self, client: TestClient
    ) -> None:
        """La saturación nunca reclasifica errores de dominio a 5xx."""
        response = client.post(
            "/extract",
            files={"file": ("corrupto.pdf", b"no-es-un-pdf", "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_PDF_CONTENT"


def response_body_message(body: dict) -> str:
    message = body.get("message")
    assert isinstance(message, str) and message, "message debe ser string no vacío"
    return message
