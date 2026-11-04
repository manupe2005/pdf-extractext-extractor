"""Configuración desde Consul KV antes de forkear workers (Issue #19)."""

import importlib.util
import logging
import os
from pathlib import Path

import pytest

from pdf_extractext_extractor import discovery
from pdf_extractext_extractor.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
GUNICORN_CONFIG = REPO_ROOT / "gunicorn.conf.py"

KV_PREFIX = "pdf-extractext/config/extraction/"
KV_KEYS = ("MAX_UPLOAD_BYTES", "MAX_CONCURRENCY", "RETRY_AFTER_SECONDS")


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
    kv_values: dict[str, str] = {}
    kv_error: Exception | None = None
    kv_prefixes: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        type(self).instances.append(self)

    def kv_list(self, prefix: str) -> dict[str, str]:
        type(self).kv_prefixes.append(prefix)
        if type(self).kv_error is not None:
            raise type(self).kv_error
        return dict(type(self).kv_values)


@pytest.fixture()
def gunicorn_module(monkeypatch):
    module = _load_gunicorn_config()
    FakeConsulClient.instances = []
    FakeConsulClient.kv_values = {}
    FakeConsulClient.kv_error = None
    FakeConsulClient.kv_prefixes = []
    monkeypatch.setattr(module.discovery, "ConsulClient", FakeConsulClient)
    monkeypatch.setenv("CONSUL_ENABLED", "true")
    for key in KV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return module


def _full_key(name: str) -> str:
    return f"{KV_PREFIX}{name}"


class TestKvPrecedence:
    def test_kv_values_fill_missing_environment(self, gunicorn_module) -> None:
        FakeConsulClient.kv_values = {
            _full_key("MAX_UPLOAD_BYTES"): "1024",
            _full_key("MAX_CONCURRENCY"): "4",
            _full_key("RETRY_AFTER_SECONDS"): "7",
        }

        gunicorn_module.on_starting(None)

        assert os.environ["MAX_UPLOAD_BYTES"] == "1024"
        assert os.environ["MAX_CONCURRENCY"] == "4"
        assert os.environ["RETRY_AFTER_SECONDS"] == "7"

    def test_environment_wins_over_kv(self, gunicorn_module, monkeypatch) -> None:
        monkeypatch.setenv("MAX_UPLOAD_BYTES", "999")
        FakeConsulClient.kv_values = {
            _full_key("MAX_UPLOAD_BYTES"): "1024",
            _full_key("MAX_CONCURRENCY"): "4",
        }

        gunicorn_module.on_starting(None)

        assert os.environ["MAX_UPLOAD_BYTES"] == "999"
        assert os.environ["MAX_CONCURRENCY"] == "4"

    def test_short_and_lowercase_keys_are_supported(self, gunicorn_module) -> None:
        FakeConsulClient.kv_values = {
            "MAX_CONCURRENCY": "2",
            _full_key("retry_after_seconds"): "5",
        }

        gunicorn_module.on_starting(None)

        assert os.environ["MAX_CONCURRENCY"] == "2"
        assert os.environ["RETRY_AFTER_SECONDS"] == "5"

    def test_reads_the_expected_recurse_prefix(self, gunicorn_module) -> None:
        gunicorn_module.on_starting(None)

        assert FakeConsulClient.kv_prefixes == [KV_PREFIX]

    def test_workers_read_the_applied_values(self, gunicorn_module) -> None:
        FakeConsulClient.kv_values = {
            _full_key("MAX_UPLOAD_BYTES"): "2048",
            _full_key("MAX_CONCURRENCY"): "3",
            _full_key("RETRY_AFTER_SECONDS"): "9",
        }

        gunicorn_module.on_starting(None)
        worker_settings = Settings(_env_file=None)

        assert worker_settings.max_upload_bytes == 2048
        assert worker_settings.max_concurrency == 3
        assert worker_settings.retry_after_seconds == 9


class TestKvFailureModes:
    def test_absent_kv_keeps_defaults_and_warns(
        self, gunicorn_module, caplog
    ) -> None:
        with caplog.at_level(logging.WARNING):
            gunicorn_module.on_starting(None)

        assert all(key not in os.environ for key in KV_KEYS)
        assert "default" in caplog.text.lower()

    def test_consul_down_keeps_defaults_and_warns(
        self, gunicorn_module, caplog
    ) -> None:
        FakeConsulClient.kv_error = discovery.ConsulError("consul caído")

        with caplog.at_level(logging.WARNING):
            gunicorn_module.on_starting(None)

        assert all(key not in os.environ for key in KV_KEYS)
        assert "consul" in caplog.text.lower()

    def test_invalid_values_are_ignored(self, gunicorn_module, caplog) -> None:
        FakeConsulClient.kv_values = {
            _full_key("MAX_UPLOAD_BYTES"): "no-es-numero",
            _full_key("MAX_CONCURRENCY"): "-3",
        }

        with caplog.at_level(logging.WARNING):
            gunicorn_module.on_starting(None)

        assert "MAX_UPLOAD_BYTES" not in os.environ
        assert "MAX_CONCURRENCY" not in os.environ

    def test_disabled_consul_does_not_touch_network(
        self, gunicorn_module, monkeypatch
    ) -> None:
        class ExplodingClient:
            def __init__(self, *args, **kwargs) -> None:
                raise AssertionError("no debe crear cliente con Consul deshabilitado")

        monkeypatch.setenv("CONSUL_ENABLED", "false")
        monkeypatch.setattr(
            gunicorn_module.discovery, "ConsulClient", ExplodingClient
        )

        gunicorn_module.on_starting(None)

        assert all(key not in os.environ for key in KV_KEYS)
