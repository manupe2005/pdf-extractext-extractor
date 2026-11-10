"""Documentación, .env.example y gate de cobertura (Issue #20)."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
MAKEFILE = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

EXPECTED_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "PORT",
    "MAX_UPLOAD_BYTES",
    "MAX_CONCURRENCY",
    "RETRY_AFTER_SECONDS",
    "WEB_CONCURRENCY",
    "GUNICORN_BACKLOG",
    "CONSUL_ENABLED",
    "CONSUL_HTTP_ADDR",
    "CONSUL_HTTP_TOKEN",
    "CONSUL_HTTP_TIMEOUT",
    "GIT_COMMIT",
)


def test_env_example_documents_every_variable() -> None:
    for name in EXPECTED_ENV_VARS:
        assert f"{name}=" in ENV_EXAMPLE, f"falta {name} en .env.example"


def test_readme_documents_consul_configuration() -> None:
    for token in (
        "CONSUL_ENABLED",
        "CONSUL_HTTP_ADDR",
        "CONSUL_HTTP_TOKEN",
        "CONSUL_HTTP_TIMEOUT",
        "GIT_COMMIT",
    ):
        assert token in README


def test_readme_documents_registration_flow() -> None:
    for token in (
        "/v1/agent/service/register",
        "/v1/agent/service/deregister",
        "extraction-<hostname>",
        "http://<address>:8001/readyz",
        "X-Consul-Token",
    ):
        assert token in README


def test_readme_documents_kv_and_traefik() -> None:
    for token in (
        "pdf-extractext/config/extraction/",
        "env > KV > default",
        "traefik.http.routers.extraction.rule",
        "traefik.http.routers.extraction.entrypoints",
        "traefik.http.routers.extraction.middlewares",
        "circuit-breaker@file",
        "traefik.http.services.extraction.loadbalancer.server.port",
    ):
        assert token in README


def test_make_test_is_the_pytest_gate() -> None:
    assert re.search(r"^test:\n\tuv run pytest -q$", MAKEFILE, re.MULTILINE)


def test_pytest_cov_is_a_dev_dependency() -> None:
    assert "pytest-cov" in PYPROJECT


def test_coverage_gate_is_eighty_percent() -> None:
    assert "[tool.coverage.run]" in PYPROJECT
    assert "fail_under = 80" in PYPROJECT
