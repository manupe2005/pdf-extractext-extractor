.PHONY: test smoke load-test stress-test profile perf-sustained

test:
	uv run pytest -q

# Smoke de liveness contra el contenedor con límites aplicados.
smoke:
	docker compose build
	docker compose up -d --wait
	docker compose exec -T extraction python -c \
		"import urllib.request, sys; r = urllib.request.urlopen('http://127.0.0.1:8001/health'); sys.exit(0 if r.status == 200 else 1)"
	docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
	docker compose down

# Profiling manual: make profile CMD="vegeta attack ..." no reaplica; solo muestrea.
profile:
	./tests/load/profile.sh start manual; \
	echo "Ejecutando muestreo. Detener con: ./tests/load/profile.sh stop"

# ---- Performance ----
# Requisito: stack levantado (make up en ../pdf-extractext-infrastructure).

RESULTS_DIR := tests/load/results
# k6 en hosts con poca RAM: capa el heap del runtime (cliente) — los 100 VUs
# multiplican buffers del cuerpo multipart de 8.5MB.
K6_ENV := GOGC=25 GOMEMLIMIT=2500MiB

load-test: ## k6: spike 100 VUs + arrival-rate 25 rps (con profiling de CPU/RSS)
	@test -f tests/data/heavy.292.pdf || (echo "Falta tests/data/heavy.292.pdf" && exit 1)
	tests/load/profile.sh start k6-run
	$(K6_ENV) k6 run tests/load/k6_suite.js; status=$$?; \
	tests/load/profile.sh stop; exit $$status

stress-test: ## Vegeta: 50 rps x 30s contra /extract (con profiling de CPU/RSS)
	@test -f tests/load/vegeta_targets.txt || tests/load/vegeta_target.sh
	tests/load/profile.sh start vegeta-run
	vegeta attack -targets=tests/load/vegeta_targets.txt \
		-body=tests/load/vegeta_body.bin -rate=50/s -duration=30s -timeout=60s \
		| tee $(RESULTS_DIR)/vegeta-last.json | vegeta report; \
	tests/load/profile.sh stop

perf-sustained: ## Prueba sostenida 10 rps x 120s para estabilidad de memoria
	@test -f tests/load/vegeta_targets.txt || tests/load/vegeta_target.sh
	tests/load/profile.sh start sustained-run
	vegeta attack -targets=tests/load/vegeta_targets.txt \
		-body=tests/load/vegeta_body.bin -rate=10/s -duration=120s -timeout=60s \
		| vegeta report; \
	tests/load/profile.sh stop
