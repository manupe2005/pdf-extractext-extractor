.PHONY: test smoke

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
