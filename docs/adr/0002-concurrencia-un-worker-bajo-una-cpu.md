# ADR 0002: Un worker y un slot de concurrencia por réplica bajo 1 CPU / 1 GiB

Fecha: 2026-10-07 · Estado: Aceptada (validada con mediciones, Issue #9)

## Contexto

La extracción del PDF pesado (~292 páginas, 8.5 MB) es CPU-bound: ~0.17 CPU·s
por request. El servicio corre con límite de 1 CPU / 1 GiB por réplica. La
configuración previa (Gunicorn 4 workers × `max_concurrency=1`) producía
p99 > 2 s bajo carga porque los 4 procesos se time-sliceaban la misma CPU.

## Opciones medidas (Vegeta 50 rps × 30 s, mismo corpus)

| Config | 200s | p99 | RSS max |
|---|---:|---:|---:|
| 4 workers × 1 slot (baseline) | 59 | 2.91 s ❌ | 601 MiB |
| **1 worker × 1 slot** | **111** | **0.37 s** ✓ | **190 MiB** |
| 2 workers × 1 slot | 91 | 0.91 s | 307 MiB |
| 1 worker × 2 slots | 112 | 0.65 s | — |

## Decisión

`WEB_CONCURRENCY=1`, `MAX_CONCURRENCY=1` por réplica, parametrizados vía
variables de entorno en el compose de infraestructura (`EXTRACTION_WORKERS`,
`EXTRACTION_MAX_CONCURRENCY`). Los límites 1 CPU / 1 GiB NO se tocan.

## Consecuencias

- Positivas: p99 en verde (k6 559 ms, Vegeta 568 ms), 0 OOM/restarts, RSS
  plano ~150 MiB, throughput real máximo (CPU saturada de forma útil).
- Negativas/aceptadas: la sobredemanda se devuelve como 503 controlado
  (instantáneo, con Retry-After) en vez de encolarse; los tests excluyen 503
  del error rate por diseño de la Issue #8. El throughput de extracciones
  exitosas (~3.7 rps/réplica) solo crece añadiendo réplicas en un host con
  CPU sobrada (ver comparación 1 vs 5 réplicas en `docs/performance-issue-9.md`).
