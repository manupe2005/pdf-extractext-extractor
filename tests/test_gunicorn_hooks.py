"""Hooks del master de Gunicorn para registro en Consul (Issue #18)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdf_extractext_extractor import discovery

REPO_ROOT = Path(__file__).resolve().parents[1]
GUNICORN_CONFIG = REPO_ROOT / "gunicorn.conf.py"

EXPECTED_TAGS = [
    "traefik.enable=true",
    "traefik.http.routers.extraction.rule=Host(`extraction.pdf-extractext.localhost`)",
    "traefik.http.routers.extraction.entrypoints=internal",
    "traefik.http.services.extraction.loadbalancer.server.port=8001",
]

EXPECTED_META = {
    "traefik.enable": "true",
    "traefik.http.routers.extraction.rule": (
        "Host(`extraction.pdf-extractext.localhost`)"
    ),
    "traefik.http.routers.extraction.entrypoints": "internal",
    "traefik.http.services.extraction.loadbalancer.server.port": "8001",
    "version": "1.2.3",
    "commit": "deadbeef",
}


def _load_gunicorn_config():
    spec = importlib.util.spec_from_file_location(
        "gunicorn_config_under_test", GUNICORN_CONFIG
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeConsulClient:
    instances: list = []
    register_calls: list = []
    deregister_calls: list = []
    register_error: Exception | None = None
    deregister_error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.http_addr = kwargs.get("http_addr") or "http://10.255.255.1:8500"
        type(self).instances.append(self)

    def register(self, payload: dict) -> None:
        type(self).register_calls.append(payload)
        if type(self).register_error is not None:
            raise type(self).register_error

    def deregister(self, service_id: str) -> None:
        type(self).deregister_calls.append(service_id)
        if type(self).deregister_error is not None:
            raise type(self).deregister_error


@pytest.fixture()
def gunicorn_module(monkeypatch):
    module = _load_gunicorn_config()
    FakeConsulClient.instances = []
    FakeConsulClient.register_calls = []
    FakeConsulClient.deregister_calls = []
    FakeConsulClient.register_error = None
    FakeConsulClient.deregister_error = None
    monkeypatch.setattr(module.discovery, "ConsulClient", FakeConsulClient)
    monkeypatch.setattr(
        module.discovery, "resolve_local_address", lambda address=None: "10.0.0.5"
    )
    monkeypatch.setattr(module.discovery.socket, "gethostname", lambda: "host-01")
    monkeypatch.setenv("CONSUL_ENABLED", "true")
    monkeypatch.setenv("CONSUL_HTTP_ADDR", "http://10.255.255.1:8500")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("GIT_COMMIT", "deadbeef")
    return module


def _server() -> SimpleNamespace:
    return SimpleNamespace(workers=[object(), object()])


class TestWhenReady:
    def test_registers_exactly_one_instance_with_two_workers(
        self, gunicorn_module
    ) -> None:
        gunicorn_module.when_ready(_server())

        assert len(FakeConsulClient.register_calls) == 1

    def test_registration_payload_matches_contract(self, gunicorn_module) -> None:
        gunicorn_module.when_ready(_server())

        assert FakeConsulClient.register_calls == [
            {
                "ID": "extraction-host-01",
                "Name": "extraction",
                "Address": "10.0.0.5",
                "Port": 8001,
                "Tags": EXPECTED_TAGS,
                "Meta": EXPECTED_META,
                "Check": {
                    "HTTP": "http://10.0.0.5:8001/readyz",
                    "Interval": "10s",
                    "Timeout": "2s",
                    "DeregisterCriticalServiceAfter": "1m",
                },
            }
        ]

    def test_registration_is_idempotent(self, gunicorn_module) -> None:
        gunicorn_module.when_ready(_server())
        gunicorn_module.when_ready(_server())

        assert len(FakeConsulClient.register_calls) == 1

    def test_address_resolution_targets_consul_not_localhost(
        self, gunicorn_module, monkeypatch
    ) -> None:
        resolved: list[str | None] = []

        def fake_resolve(address=None):
            resolved.append(address)
            return "10.0.0.5"

        monkeypatch.setattr(
            gunicorn_module.discovery, "resolve_local_address", fake_resolve
        )

        gunicorn_module.when_ready(_server())

        assert resolved == ["http://10.255.255.1:8500"]

    def test_disabled_consul_skips_registration(self, gunicorn_module, monkeypatch) -> None:
        monkeypatch.setenv("CONSUL_ENABLED", "false")

        gunicorn_module.when_ready(_server())

        assert FakeConsulClient.instances == []
        assert FakeConsulClient.register_calls == []

    def test_consul_down_retries_with_backoff_and_does_not_raise(
        self, gunicorn_module, monkeypatch
    ) -> None:
        FakeConsulClient.register_error = discovery.ConsulError("consul caído")
        delays: list[float] = []
        monkeypatch.setattr(gunicorn_module.time, "sleep", delays.append)

        gunicorn_module.when_ready(_server())

        assert len(FakeConsulClient.register_calls) == 3
        assert delays == [0.5, 1.0]

    def test_version_and_commit_fall_back_to_defaults(
        self, gunicorn_module, monkeypatch
    ) -> None:
        monkeypatch.delenv("APP_VERSION", raising=False)
        monkeypatch.delenv("GIT_COMMIT", raising=False)

        gunicorn_module.when_ready(_server())

        meta = FakeConsulClient.register_calls[0]["Meta"]
        assert meta["version"] == "0.1.0"
        assert meta["commit"] == "unknown"


class TestOnExit:
    def test_deregisters_the_registered_id(self, gunicorn_module) -> None:
        gunicorn_module.when_ready(_server())

        gunicorn_module.on_exit(_server())

        assert FakeConsulClient.deregister_calls == ["extraction-host-01"]

    def test_deregisters_only_once(self, gunicorn_module) -> None:
        gunicorn_module.when_ready(_server())

        gunicorn_module.on_exit(_server())
        gunicorn_module.on_exit(_server())

        assert FakeConsulClient.deregister_calls == ["extraction-host-01"]

    def test_skips_deregistration_when_never_registered(self, gunicorn_module) -> None:
        gunicorn_module.on_exit(_server())

        assert FakeConsulClient.deregister_calls == []

    def test_deregistration_failure_does_not_raise(self, gunicorn_module) -> None:
        FakeConsulClient.deregister_error = discovery.ConsulError("consul caído")
        gunicorn_module.when_ready(_server())

        gunicorn_module.on_exit(_server())


class TestGunicornConfig:
    def test_graceful_timeout_is_thirty_seconds(self, gunicorn_module) -> None:
        assert gunicorn_module.graceful_timeout == 30
