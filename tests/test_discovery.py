"""Cliente Consul sin dependencias externas (Issue #17)."""

import base64
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pdf_extractext_extractor import discovery
from pdf_extractext_extractor.config import Settings


class _RecordingHandler(BaseHTTPRequestHandler):
    """Servidor local que registra método, path, headers y body."""

    requests: list[dict] = []
    response_status = 200
    response_body = b""
    delay = 0.0

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        if type(self).delay:
            time.sleep(type(self).delay)
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        try:
            self.wfile.write(type(self).response_body)
        except BrokenPipeError:
            pass

    do_GET = _handle
    do_PUT = _handle

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def consul_server():
    _RecordingHandler.requests = []
    _RecordingHandler.response_status = 200
    _RecordingHandler.response_body = b""
    _RecordingHandler.delay = 0.0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, _RecordingHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _client(server: ThreadingHTTPServer, **kwargs) -> discovery.ConsulClient:
    host, port = server.server_address
    return discovery.ConsulClient(http_addr=f"http://{host}:{port}", **kwargs)


class TestConsulRequests:
    def test_register_sends_put_payload(self, consul_server) -> None:
        server, handler = consul_server
        payload = {
            "ID": "extraction-host",
            "Name": "extraction",
            "Address": "10.0.0.5",
            "Port": 8001,
        }

        _client(server).register(payload)

        request = handler.requests[-1]
        assert request["method"] == "PUT"
        assert request["path"] == "/v1/agent/service/register"
        assert json.loads(request["body"]) == payload

    def test_token_header_is_sent_when_env_is_defined(
        self, consul_server, monkeypatch
    ) -> None:
        server, handler = consul_server
        monkeypatch.setenv("CONSUL_HTTP_TOKEN", "token-secreto")

        _client(server).deregister("extraction-host")

        assert handler.requests[-1]["headers"]["X-Consul-Token"] == "token-secreto"

    def test_token_header_is_omitted_when_env_is_absent(
        self, consul_server, monkeypatch
    ) -> None:
        server, handler = consul_server
        monkeypatch.delenv("CONSUL_HTTP_TOKEN", raising=False)

        _client(server, token="").deregister("extraction-host")

        assert "X-Consul-Token" not in handler.requests[-1]["headers"]

    def test_explicit_token_overrides_environment(self, consul_server, monkeypatch) -> None:
        server, handler = consul_server
        monkeypatch.setenv("CONSUL_HTTP_TOKEN", "desde-entorno")

        _client(server, token="explicito").deregister("extraction-host")

        assert handler.requests[-1]["headers"]["X-Consul-Token"] == "explicito"

    def test_deregister_encodes_service_id(self, consul_server) -> None:
        server, handler = consul_server

        _client(server).deregister("extraction/host name")

        assert (
            handler.requests[-1]["path"]
            == "/v1/agent/service/deregister/extraction%2Fhost%20name"
        )

    def test_health_passing_reports_true_with_instances(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_body = json.dumps([{"Service": {"ID": "extraction-host"}}]).encode()

        result = _client(server).health_passing("extraction")

        assert result is True
        assert handler.requests[-1]["path"] == "/v1/health/service/extraction?passing=true"

    def test_health_passing_reports_false_without_instances(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_body = b"[]"

        assert _client(server).health_passing("extraction") is False

    def test_health_passing_reports_false_on_404(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_status = 404
        handler.response_body = b""

        assert _client(server).health_passing("extraction") is False

    def test_kv_list_decodes_base64_and_requests_recurse(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_body = json.dumps(
            [
                {
                    "Key": "pdf-extractext/config/extraction/MAX_UPLOAD_BYTES",
                    "Value": base64.b64encode(b"1024").decode("ascii"),
                },
                {
                    "Key": "pdf-extractext/config/extraction/FLAG",
                    "Value": None,
                },
            ]
        ).encode()

        values = _client(server).kv_list("pdf-extractext/config/extraction/")

        assert handler.requests[-1]["path"] == (
            "/v1/kv/pdf-extractext/config/extraction/?recurse"
        )
        assert values == {
            "pdf-extractext/config/extraction/MAX_UPLOAD_BYTES": "1024",
            "pdf-extractext/config/extraction/FLAG": "",
        }

    def test_kv_list_returns_empty_mapping_on_404(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_status = 404
        handler.response_body = b""

        assert _client(server).kv_list("prefijo/ausente/") == {}

    def test_http_error_raises_consul_error(self, consul_server) -> None:
        server, handler = consul_server
        handler.response_status = 500
        handler.response_body = b"boom"

        with pytest.raises(discovery.ConsulError):
            _client(server).register({"ID": "extraction-host"})

    def test_connection_error_raises_consul_error(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        client = discovery.ConsulClient(
            http_addr=f"http://127.0.0.1:{port}", timeout=0.2
        )

        with pytest.raises(discovery.ConsulError):
            client.health_passing("extraction")

    def test_timeout_is_enforced(self, consul_server) -> None:
        server, handler = consul_server
        handler.delay = 0.3

        with pytest.raises(discovery.ConsulError):
            _client(server, timeout=0.05).health_passing("extraction")

    def test_timeout_and_address_are_configurable(self, monkeypatch) -> None:
        monkeypatch.delenv("CONSUL_HTTP_TIMEOUT", raising=False)
        monkeypatch.delenv("CONSUL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.setenv("CONSUL_HTTP_ADDR", "http://consul:8500")

        default_client = discovery.ConsulClient()
        assert default_client.timeout == 2.0
        assert default_client.http_addr == "http://consul:8500"

        monkeypatch.setenv("CONSUL_HTTP_TIMEOUT", "0.75")
        assert discovery.ConsulClient().timeout == 0.75

    def test_module_level_wrappers_delegate_to_client(self, monkeypatch) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            def register(self, payload: dict) -> None:
                self.calls.append(("register", payload))

            def deregister(self, service_id: str) -> None:
                self.calls.append(("deregister", service_id))

            def health_passing(self, name: str) -> bool:
                self.calls.append(("health", name))
                return True

            def kv_list(self, prefix: str) -> dict[str, str]:
                self.calls.append(("kv", prefix))
                return {}

        fake = FakeClient()
        monkeypatch.setattr(discovery, "default_client", lambda: fake)

        discovery.register({"ID": "extraction-host"})
        discovery.deregister("extraction-host")
        assert discovery.health_passing("extraction") is True
        assert discovery.kv_list("prefijo/") == {}

        assert fake.calls == [
            ("register", {"ID": "extraction-host"}),
            ("deregister", "extraction-host"),
            ("health", "extraction"),
            ("kv", "prefijo/"),
        ]


class TestServiceRegistration:
    def test_service_id_uses_hostname(self, monkeypatch) -> None:
        monkeypatch.setattr(discovery.socket, "gethostname", lambda: "host-01")

        assert discovery.service_id() == "extraction-host-01"

    def test_traefik_tags_match_contract(self) -> None:
        assert discovery.traefik_tags() == [
            "traefik.enable=true",
            "traefik.http.routers.extraction.rule=Host(`extraction.pdf-extractext.localhost`)",
            "traefik.http.routers.extraction.entrypoints=internal",
            "traefik.http.routers.extraction.middlewares=circuit-breaker@file",
            "traefik.http.services.extraction.loadbalancer.server.port=8001",
        ]

    def test_traefik_meta_mirrors_tags_and_adds_version_commit(self) -> None:
        meta = discovery.traefik_meta("1.2.3", "deadbeef")

        assert meta == {
            "traefik.enable": "true",
            "traefik.http.routers.extraction.rule": (
                "Host(`extraction.pdf-extractext.localhost`)"
            ),
            "traefik.http.routers.extraction.entrypoints": "internal",
            "traefik.http.routers.extraction.middlewares": "circuit-breaker@file",
            "traefik.http.services.extraction.loadbalancer.server.port": "8001",
            "version": "1.2.3",
            "commit": "deadbeef",
        }

    def test_registration_payload_contains_check_and_metadata(self) -> None:
        payload = discovery.build_service_registration(
            service_id="extraction-host-01",
            address="10.0.0.5",
            version="1.2.3",
            commit="deadbeef",
        )

        assert payload == {
            "ID": "extraction-host-01",
            "Name": "extraction",
            "Address": "10.0.0.5",
            "Port": 8001,
            "Tags": discovery.traefik_tags(),
            "Meta": discovery.traefik_meta("1.2.3", "deadbeef"),
            "Check": {
                "HTTP": "http://10.0.0.5:8001/readyz",
                "Interval": "10s",
                "Timeout": "2s",
                "DeregisterCriticalServiceAfter": "1m",
            },
        }

    def test_resolve_local_address_uses_udp_toward_consul(self, monkeypatch) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.destination = None

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def connect(self, destination: tuple[str, int]) -> None:
                self.destination = destination

            def getsockname(self) -> tuple[str, int]:
                return ("10.1.2.3", 54321)

        fake = FakeSocket()
        calls = {}

        def fake_socket(family, type_):
            calls["family"] = family
            calls["type"] = type_
            return fake

        monkeypatch.setattr(discovery.socket, "socket", fake_socket)

        address = discovery.resolve_local_address("http://consul.service:8500")

        assert address == "10.1.2.3"
        assert fake.destination == ("consul.service", 8500)
        assert calls == {"family": socket.AF_INET, "type": socket.SOCK_DGRAM}

    def test_resolve_local_address_falls_back_from_loopback(self, monkeypatch) -> None:
        class LoopbackSocket:
            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def connect(self, destination: tuple[str, int]) -> None:
                pass

            def getsockname(self) -> tuple[str, int]:
                return ("127.0.0.1", 54321)

        monkeypatch.setattr(
            discovery.socket, "socket", lambda *args: LoopbackSocket()
        )
        monkeypatch.setattr(
            discovery.socket, "gethostbyname", lambda host: "10.9.8.7"
        )

        assert discovery.resolve_local_address("http://127.0.0.1:8500") == "10.9.8.7"

    def test_resolve_local_address_wraps_socket_errors(self, monkeypatch) -> None:
        class BrokenSocket:
            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def connect(self, destination: tuple[str, int]) -> None:
                raise OSError("sin ruta")

        monkeypatch.setattr(
            discovery.socket, "socket", lambda *args: BrokenSocket()
        )

        with pytest.raises(discovery.ConsulError):
            discovery.resolve_local_address("http://consul.service:8500")


class TestConsulSettings:
    def test_consul_is_disabled_by_default(self, monkeypatch) -> None:
        for name in (
            "CONSUL_ENABLED",
            "CONSUL_HTTP_ADDR",
            "CONSUL_HTTP_TOKEN",
            "CONSUL_HTTP_TIMEOUT",
        ):
            monkeypatch.delenv(name, raising=False)

        settings = Settings(_env_file=None)

        assert settings.consul_enabled is False
        assert settings.consul_http_addr == "http://127.0.0.1:8500"
        assert settings.consul_http_token is None
        assert settings.consul_http_timeout == 2.0

    def test_consul_settings_read_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("CONSUL_ENABLED", "true")
        monkeypatch.setenv("CONSUL_HTTP_ADDR", "http://consul:8500")
        monkeypatch.setenv("CONSUL_HTTP_TOKEN", "secreto")
        monkeypatch.setenv("CONSUL_HTTP_TIMEOUT", "0.5")

        settings = Settings(_env_file=None)

        assert settings.consul_enabled is True
        assert settings.consul_http_addr == "http://consul:8500"
        assert settings.consul_http_token == "secreto"
        assert settings.consul_http_timeout == 0.5
