"""Verifica sin Docker el endurecimiento del Dockerfile y del compose local."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")


class TestDockerfile:
    def test_is_multistage(self) -> None:
        assert len(re.findall(r"^FROM ", DOCKERFILE, re.MULTILINE)) >= 2

    def test_runs_as_non_root_user(self) -> None:
        assert re.search(r"^USER (?!root\b)\w+", DOCKERFILE, re.MULTILINE)
        assert "useradd" in DOCKERFILE

    def test_uses_frozen_lockfile_without_dev_dependencies(self) -> None:
        assert "uv.lock" in DOCKERFILE
        assert "--locked" in DOCKERFILE
        assert "--no-dev" in DOCKERFILE

    def test_has_healthcheck(self) -> None:
        assert "HEALTHCHECK" in DOCKERFILE

    def test_runs_gunicorn(self) -> None:
        assert "gunicorn" in DOCKERFILE

    def test_uv_image_is_version_pinned(self) -> None:
        match = re.search(r"ghcr\.io/astral-sh/uv:(\S+)", DOCKERFILE)
        assert match, "la imagen de uv debe estar fijada por versión"
        assert match.group(1) not in {"latest", ""}

    def test_runtime_applies_debian_patches_before_user(self) -> None:
        """Trivy: parches del SO se aplican como root en build del runtime,
        antes de bajar a USER appuser."""
        stage2 = DOCKERFILE[DOCKERFILE.rfind("FROM python:3.12-slim") :]
        assert "apt-get update && apt-get upgrade -y" in stage2
        assert "rm -rf /var/lib/apt/lists/*" in stage2
        assert stage2.find("apt-get upgrade") < stage2.find("useradd")
        assert "USER appuser" in stage2


class TestComposeLocal:
    def test_applies_explicit_resource_limits(self) -> None:
        assert 'cpus: "1.0"' in COMPOSE
        assert "memory: 1g" in COMPOSE
        assert "limits:" in COMPOSE

    def test_never_publishes_ports(self) -> None:
        assert not re.search(r"^\s*ports:", COMPOSE, re.MULTILINE)
        assert re.search(r"^\s*expose:", COMPOSE, re.MULTILINE)
        assert re.search(r"internal:\s*true", COMPOSE)

    def test_has_liveness_healthcheck(self) -> None:
        assert "healthcheck:" in COMPOSE
        assert "/health" in COMPOSE

    def test_concurrency_is_parametrized(self) -> None:
        assert "WEB_CONCURRENCY" in COMPOSE
        assert "MAX_CONCURRENCY" in COMPOSE

    def test_disables_privilege_escalation(self) -> None:
        """no-new-privileges: bloquea setuid/sudo dentro del contenedor."""
        assert "security_opt:" in COMPOSE
        assert "no-new-privileges:true" in COMPOSE
