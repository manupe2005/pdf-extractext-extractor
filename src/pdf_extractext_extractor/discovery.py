"""Cliente mínimo de HashiCorp Consul usando solo la librería estándar."""

from __future__ import annotations

import base64
import binascii
import json
import os
import socket
from urllib import error, parse, request

DEFAULT_HTTP_ADDR = "http://127.0.0.1:8500"
DEFAULT_TIMEOUT_SECONDS = 2.0
TOKEN_HEADER = "X-Consul-Token"
SERVICE_NAME = "extraction"
SERVICE_PORT = 8001
KV_CONFIG_PREFIX = "pdf-extractext/config/extraction/"
TRAEFIK_ROUTER = "extraction"
TRAEFIK_HOST = "extraction.pdf-extractext.localhost"
TRAEFIK_SERVICE_PORT_KEY = (
    f"traefik.http.services.{TRAEFIK_ROUTER}.loadbalancer.server.port"
)


class ConsulError(RuntimeError):
    """Fallo de comunicación o respuesta inválida de Consul."""


def _normalize_http_addr(http_addr: str) -> str:
    address = http_addr.strip()
    if "://" not in address:
        address = f"http://{address}"
    return address.rstrip("/")


def _timeout_from_env() -> float:
    for name in ("CONSUL_HTTP_TIMEOUT", "CONSUL_TIMEOUT_SECONDS"):
        raw = os.getenv(name)
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return DEFAULT_TIMEOUT_SECONDS


def _decode_value(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConsulError("Consul devolvió un valor KV no textual.")
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ConsulError("Consul devolvió un valor KV no base64 UTF-8.") from exc


def _raise_for_status(status: int, action: str) -> None:
    if not 200 <= status < 300:
        raise ConsulError(f"No se pudo {action} en Consul (HTTP {status}).")


class ConsulClient:
    """Cliente HTTP con token, timeout y operaciones de agente y KV."""

    def __init__(
        self,
        http_addr: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        address = http_addr or os.getenv("CONSUL_HTTP_ADDR", DEFAULT_HTTP_ADDR)
        self.http_addr = _normalize_http_addr(address)
        self.token = token
        self.timeout = timeout if timeout is not None else _timeout_from_env()

    def _request(
        self, method: str, path: str, payload: dict | None = None
    ) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        token = self.token if self.token is not None else os.getenv("CONSUL_HTTP_TOKEN")
        if token:
            headers[TOKEN_HEADER] = token
        if data is not None:
            headers["Content-Type"] = "application/json"

        consul_request = request.Request(
            f"{self.http_addr}{path}", data=data, headers=headers, method=method
        )
        try:
            with request.urlopen(consul_request, timeout=self.timeout) as response:
                return response.status, response.read()
        except error.HTTPError as exc:
            return exc.code, exc.read()
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ConsulError(
                f"Consul no disponible en {self.http_addr}: {exc}"
            ) from exc

    def register(self, payload: dict) -> None:
        status, _ = self._request("PUT", "/v1/agent/service/register", payload)
        _raise_for_status(status, "registrar el servicio")

    def deregister(self, service_id: str) -> None:
        encoded_id = parse.quote(service_id, safe="")
        status, _ = self._request(
            "PUT", f"/v1/agent/service/deregister/{encoded_id}"
        )
        _raise_for_status(status, "deregistrar el servicio")

    def health_passing(self, name: str) -> bool:
        encoded_name = parse.quote(name, safe="")
        status, body = self._request(
            "GET", f"/v1/health/service/{encoded_name}?passing=true"
        )
        if status == 404:
            return False
        _raise_for_status(status, f"consultar la salud de {name}")
        try:
            instances = json.loads(body or b"[]")
        except json.JSONDecodeError as exc:
            raise ConsulError("Consul devolvió un health no JSON.") from exc
        return isinstance(instances, list) and bool(instances)

    def kv_list(self, prefix: str) -> dict[str, str]:
        encoded_prefix = parse.quote(prefix.lstrip("/"), safe="/")
        status, body = self._request("GET", f"/v1/kv/{encoded_prefix}?recurse")
        if status == 404:
            return {}
        _raise_for_status(status, f"leer KV {prefix}")
        try:
            items = json.loads(body or b"[]")
        except json.JSONDecodeError as exc:
            raise ConsulError("Consul devolvió un KV no JSON.") from exc
        if not isinstance(items, list):
            raise ConsulError("Consul devolvió un KV con formato inesperado.")

        values: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("Key")
            if not isinstance(key, str) or not key:
                continue
            values[key] = _decode_value(item.get("Value"))
        return values


def default_client() -> ConsulClient:
    return ConsulClient()


def register(payload: dict, client: ConsulClient | None = None) -> None:
    (client or default_client()).register(payload)


def deregister(service_id: str, client: ConsulClient | None = None) -> None:
    (client or default_client()).deregister(service_id)


def health_passing(name: str, client: ConsulClient | None = None) -> bool:
    return (client or default_client()).health_passing(name)


def kv_list(prefix: str, client: ConsulClient | None = None) -> dict[str, str]:
    return (client or default_client()).kv_list(prefix)


def service_id(hostname: str | None = None) -> str:
    return f"{SERVICE_NAME}-{hostname or socket.gethostname()}"


def resolve_local_address(consul_http_addr: str | None = None) -> str:
    address = _normalize_http_addr(
        consul_http_addr or os.getenv("CONSUL_HTTP_ADDR", DEFAULT_HTTP_ADDR)
    )
    parsed = parse.urlparse(address)
    host = parsed.hostname
    if not host:
        raise ConsulError(f"Dirección de Consul inválida: {address!r}")
    port = parsed.port or 8500

    try:
        # Un socket UDP hacia Consul revela la IP de salida sin enviar tráfico.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, port))
            local_address = sock.getsockname()[0]
    except OSError as exc:
        raise ConsulError(f"No se pudo resolver la IP local: {exc}") from exc

    if local_address.startswith("127.") or local_address == "::1":
        try:
            fallback = socket.gethostbyname(socket.gethostname())
        except OSError:
            return local_address
        if not fallback.startswith("127."):
            return fallback
    return local_address


def traefik_tags(port: int = SERVICE_PORT) -> list[str]:
    return [
        "traefik.enable=true",
        f"traefik.http.routers.{TRAEFIK_ROUTER}.rule=Host(`{TRAEFIK_HOST}`)",
        f"traefik.http.routers.{TRAEFIK_ROUTER}.entrypoints=internal",
        f"{TRAEFIK_SERVICE_PORT_KEY}={port}",
    ]


def traefik_meta(version: str, commit: str, port: int = SERVICE_PORT) -> dict[str, str]:
    return {
        "traefik.enable": "true",
        f"traefik.http.routers.{TRAEFIK_ROUTER}.rule": f"Host(`{TRAEFIK_HOST}`)",
        f"traefik.http.routers.{TRAEFIK_ROUTER}.entrypoints": "internal",
        TRAEFIK_SERVICE_PORT_KEY: str(port),
        "version": version,
        "commit": commit,
    }


def build_service_registration(
    service_id: str,
    address: str,
    port: int = SERVICE_PORT,
    version: str = "0.1.0",
    commit: str = "unknown",
) -> dict:
    return {
        "ID": service_id,
        "Name": SERVICE_NAME,
        "Address": address,
        "Port": port,
        "Tags": traefik_tags(port),
        "Meta": traefik_meta(version, commit, port),
        "Check": {
            "HTTP": f"http://{address}:{port}/readyz",
            "Interval": "10s",
            "Timeout": "2s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }
