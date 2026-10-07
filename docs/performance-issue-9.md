# Issue #9 — Optimización de CPU/RAM basada en mediciones reales

Fecha: 2026-10-07 · Entorno: host local WSL (5.7 GB RAM totales, 8 vCPU lógicas),
Docker Compose del repo `pdf-extractext-infrastructure`, límites del servicio
**1 CPU / 1 GiB** (sin modificar). Corpus: `tests/data/heavy.292.pdf` (8.5 MB, ~292 páginas).

## 1. Qué se midió

Por cada corrida (`tests/load/profile.sh` + k6/Vegeta), volcados en `tests/load/results/`:

- CPU% y RSS del/los contenedor(es) de extracción (muestreo 1 s).
- Restarts y OOMKilled (`docker inspect` antes/después).
- RSS en reposo antes de la carga y ~30 s después de terminar (estabilidad de memoria).
- Métricas de k6 (spike 100 VUs + arrival-rate 25 rps) y Vegeta (50 rps × 30 s).

## 2. Baseline

### 2a. Imagen desactualizada (estado heredado del entorno)

El contenedor corriendo ejecutaba **uvicorn standalone, 1 solo proceso, sin
AdmissionMiddleware** (imagen anterior a Issues #6/#7 — el CMD del Dockerfile no
era el vigente). Resultados: **OOM kill del worker bajo 50 rps (`Memory cgroup
out of memory`, RSS 1.02 GiB = límite)**, 516 × 502, 939 timeouts, success 3%,
restarts 0→1, p99 = 30 s. Detectado gracias a la medición; se alineó la imagen
con el código del repo antes de continuar.

### 2b. Baseline real (código del repo: Gunicorn, WEB_CONCURRENCY=4, MAX_CONCURRENCY=1)

| Métrica | k6 (spike+arrival) | Vegeta 50 rps |
|---|---:|---:|
| Requests | 4820 (43.3/s) | 1500 (50/s) |
| 200 | 210 (~1.9 rps) | 59 (~2.0 rps) |
| 503 controlados | 4610 (95.6 %) | 1441 (96.1 %) |
| Errores ≠503 | 0.00 % | 0 |
| p99 | **2.04 s** ❌ | **2.91 s** ❌ |
| RSS max / reposo | 598 / 589 MiB | 601 / 589 MiB |
| CPU media | 93.7 % | 102 % |
| Restarts / OOM | 0 / no ✓ | 0 / no ✓ |

Diagnóstico: **cuello CPU-bound**. Cada extracción de ~292 páginas consume
~0.17 CPU·s → capacidad teórica ≈ 5.9 rps por CPU. Con 4 workers en **1 sola
CPU**, 4 extracciones simultáneas se time-slicean: cada 200 tarda ~4× más sin
ganar throughput. La cola del semáforo (1 por worker) no evita ese solapamiento.

### Estabilidad de memoria (código actual)

En ninguna corrida del código actual se observó crecimiento sostenido de RSS:
repsoso tras carga ≈ baseline (589 → 589 MiB; en config final 149.6 → 149.0 MiB).
**No se afirma fuga de memoria**: la curva es un plateau, no una pendiente
monótona; la retención vista en la imagen heredada (1.2 MB/request) era el
backlog de requests encoladas en un único proceso sin control de admisión.

## 3. Experimentos (todos bajo 1 CPU / 1 GiB, Vegeta 50 rps × 30 s)

| Config | 200s | p99 | RSS max | CPU | Resultado |
|---|---:|---:|---:|---:|---|
| B0: 4 workers × 1 slot | 59 | 2.91 s ❌ | 601 MiB | 102 % | baseline |
| C1: 1 worker × 1 slot | **111** | **0.37 s** ✓ | **190 MiB** | 105 % | **elegida** |
| C2: 2 workers × 1 slot | 91 | 0.91 s ✓ | 307 MiB | 91.5 % | peor que C1 |
| C4: 1 worker × 2 slots | 112 | 0.65 s ✓ | — | — | sin ganancia vs C1 |

Conclusión: en carga CPU-bound con 1 vCPU, minimizar procesos y concurrencia
maximiza el throughput real y minimiza p99 y RAM. Ver `docs/adr/0002-*`.

## 4. Configuración final elegida

| Parámetro | Antes | Después | Justificación (métrica) |
|---|---:|---:|---|
| `WEB_CONCURRENCY` | 4 | **1** | C1: +88 % 200s, p99 2.91→0.37 s, RAM ×3 menor |
| `MAX_CONCURRENCY` | 1 | **1** | Sin cambio; C4 mostró que 2 no aporta |
| `GUNICORN_BACKLOG` | 64 | **64** | Sin evidencia de problema; no se toca |
| Límites CPU/RAM | 1 / 1 GiB | **sin cambio** | No se justificó aumento |
| `deploy.replicas` | 1 | **1** (default) | Ver comparación abajo |

Todo ello ya parametrizable por env: compose expone `EXTRACTION_WORKERS`,
`EXTRACTION_MAX_CONCURRENCY`, `EXTRACTION_RETRY_AFTER_SECONDS` (defaults en
`.env.example` = configuración medida).

## 5. Resultados finales (config definitiva, 1 réplica)

### k6 (`make load-test`) — EXIT 0, todos los thresholds en verde ✓

```
spike 100 VUs completado sin crash ✓
arrival-rate 25 rps completado, dropped_iterations = 16 (0.14 %)
http_reqs: 4341 (39.3/s)
p(99) = 559 ms ✓ (< 2000)
error rate ≠503: 0.00 % ✓ (< 1 %)
RSS: 149.6 → max 162 → 149.0 MiB (plano, sin fuga) ✓
Restarts: 0, OOMKilled: no ✓
```

### Vegeta (`make stress-test`) ✓

```
50 rps × 30 s: 1500 requests, 0 errores de conexión/servidor
200:80 · 503:1420 (rechazos controlados, instantáneos, med ~7 ms)
p99 = 568 ms ✓ (< 2 s) · throughput 200s ≈ 2.6 rps
RSS post-reposo: 149 MiB (≈ baseline) ✓ · 0 restarts
```

## 6. Comparación 1 vs 5 réplicas (misma config C1)

| Métrica | 1 réplica | 5 réplicas |
|---|---:|---:|
| Vegeta 200s | 80 (5.3 %) | **297 (19.8 %)** |
| Vegeta p99 | 568 ms | 812 ms |
| k6 p99 | **559 ms** ✓ | **2900 ms** ❌ |
| RSS total | ~150 MiB | ~790 MiB |
| Restarts | 0 | 0 |

Lectura honesta: 5 réplicas multiplican el throughput de 200s (~2.7×), pero en
este host pequeño (8 vCPU compartidas con k6/Traefik empujando ~280 MB/s de
payload) el p99 de k6 empeora por contención. **No se asume que 5 es mejor**:
con estos datos, el default queda en 1 réplica; la opción de escalar queda
documentada y disponible vía `docker compose up -d --scale extraction=N`,
a reevaluar con Gonzalo en infraestructura con más CPU de host.

## 7. Archivos modificados / creados

Repo extractor:
- `tests/load/profile.sh` (nuevo): muestreo CPU/RSS/restarts + resúmenes.
- `tests/load/results/` (nuevo): evidencia cruda (CSV, metas, logs).
- `tests/load/k6_suite.js`: fix de cliente — body multipart construido una única
  vez (init context) en vez de `http.file()` por iteración (OOM del proceso k6,
  3.2 GB RSS en host de 5.7 GB). Escenarios y thresholds **sin cambios**.
- `Makefile`: restaurados/mejorados `load-test`, `stress-test` + `perf-sustained`
  (incluyen profiling automático y `GOGC/GOMEMLIMIT` para k6).
- `docs/performance-issue-9.md` (este reporte), `docs/adr/0002-*.md`.

Repo infraestructura (coordinado, cambios declarativos mínimos):
- `docker-compose.yml`: passthrough de env de concurrencia con defaults medidos.
- `.env.example`: documenta `EXTRACTION_WORKERS=1`, `EXTRACTION_MAX_CONCURRENCY=1`.

Sin cambios en `src/` (la lógica del endpoint no se tocó).

## 8. Reproducibilidad

```bash
# Stack (desde ../pdf-extractext-infrastructure)
docker compose up -d

# Baseline / tuning
tests/load/profile.sh start <run_id>     # abrir otra terminal para correr k6/vegeta
tests/load/profile.sh stop && tests/load/profile.sh finish <run_id>
tests/load/profile.sh summary <run_id>

# Suites de la Issue #8
make load-test        # k6 (spike 100 VUs + arrival 25 rps)
make stress-test      # vegeta 50 rps x 30 s
make perf-sustained   # 10 rps x 120 s para estabilidad de memoria

# Comparación de réplicas
docker compose -f ../pdf-extractext-infrastructure/docker-compose.yml \
  up -d --scale extraction=5
```

Nota de entorno: k6 cliente requiere `GOGC=25 GOMEMLIMIT=2500MiB` (ya en el
Makefile) en hosts con ~5 GB RAM; el cuerpo multipart de 8.5 MB multiplica
buffers por VU. Esto es una limitación del host de pruebas, no del servicio.

## 9. Pendientes explícitos

- **Throughput de 200s acotado a ~3.7 rps/réplica (CPU)**: bajo 1 CPU no hay
  solución de tuning posible; escalar réplicas en un host con CPU real sobrada
  es el camino (coordinación con Infraestructura, Fase 9).
- En host recargado, 5 réplicas degradan p99 de k6 — reevaluar tras migrar.
