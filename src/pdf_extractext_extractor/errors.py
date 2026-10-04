"""Contrato de error estructural de la API.

Toda falla de validación estructural de la petición responde exactamente:

    400 -> {"code": "INVALID_REQUEST", "message": "<detalle>"}
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class InvalidRequest(Exception):
    """Fallo estructural de la petición: el cliente envió algo inválido."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def invalid_request_handler(request: Request, exc: InvalidRequest) -> JSONResponse:
    """Traduce InvalidRequest al contrato de error 400 exacto."""
    return JSONResponse(
        status_code=400,
        content={"code": "INVALID_REQUEST", "message": exc.message},
    )
