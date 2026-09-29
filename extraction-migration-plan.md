# Extraction Migration Plan — Proyecto Cabras

> **Estado:** PLAN APROBADO-PROPUESTO. Documento de migración generado desde el monolito.
> **Objetivo:** guiar la construcción del nuevo Extraction Service (repo separado), reutilizando como referencia la lógica verificada del monolito sin acoplarla.
> **Fuentes de verdad:** `docs/architecture/microservices-alignment-analysis.md` (B1, B2, B3, R3), `docs/specs/extraction-service.md` (C1), `docs/specs/common.md`, `docs/master-plans/extraction-service.md`, TP de Carga y Estrés.
> **Código de referencia (NO se copia acoplado):** `app/services/pdf_service.py::extract_text` (fitz/PyMuPDF) y `app/services/checksum.py` (SHA-256 delta).

---

## 1. Análisis Tecnológico — Selección de Stack

### 1.1 Veredicto: **mantener Python + PyMuPDF, con runtime HTTP desacoplado del procesamiento CPU-bound**

**No se migra el core a Go/Rust.** Justificación:

1. **El hot path ya es nativo.** PyMuPDF (`fitz`) es binding sobre MuPDF (C). La extracción de texto transpira en código nativo, no en el intérprete Python. Migrar a Go (`pdfcpu`, `ledongthuc/pdf`) o Rust (`lopdf`) implica librerías **menos maduras y menos performantes** que MuPDF, o terminar bindeando MuPDF en C de todos modos. El argumento "Python es lento" no aplica a este workload.
2. **Evidencia en el monolito:** `PDFService.extract_text` procesa PDFs de ~300 páginas completamente en memoria (`fitz.open(stream=bytes, filetype="pdf")` + `page.get_text()`). Es correcto, testeado y cumple el contrato.
3. **El riesgo real no es el lenguaje, es el modelo de concurrencia:** el event loop asyncio se bloquea ante trabajo CPU-bound. La solución es **aislamiento por procesos**, no cambio de lenguaje.

### 1.2 Configuración del runtime (estimación inicial, a validar con benchmarks del TP)

| Componente | Elección | Razón |
|---|---|---|
| Framework HTTP | FastAPI / Starlette puro (ASGI) | Estándar del proyecto, multipart nativo (python-multipart) |
| Servidor | Gunicorn + workers Uvicorn | Pool de procesos = unidad de aislamiento real ante GIL |
| Workers | ~4 por contenedor (parametrizable por env) | 1 CPU: extracción es nativa y mayormente single-thread; 4 procesos permiten absorber ráfagas sin OOM |
| Librería PDF | PyMuPDF (versión fijada en lock) | Continuidad con comportamiento verificado |
| Checksum | `hashlib.sha256(bytes).hexdigest()` | Idéntico a `common.md` §1 |
| Memoria | Todo en memoria, **cero escrituras a disco** | Explícito en TP y Master Plan §9; headroom para PDFs de ~50 MB dentro de 1GB |

### 1.3 Por qué NO Go/Rust (registro de trade-off)

- Go: excelente HTTP runtime, pero la extracción PDF sería la pieza débil (librerías inmaduras → riesgo de texto corrupto/missing → violación silenciosa de C1).
- Rust: safety + perf, pero el ecosistema PDF en Rust es joven; costo de desarrollo alto para un beneficio que ya provee MuPDF vía binding.
- Conclusión: **el cuello de botella (parseo PDF) es idéntico en los tres stacks porque es el mismo motor nativo en el mejor de los casos.** Python con procesos aislados maximiza reutilización y minimiza riesgo contractual.

---

## 2. Estrategia de Concurrencia y Backpressure

### 2.1 Modelo

    Traefik/Caddy (balanceo, hasta 5 réplicas)
       └─► Contenedor (limits: 1.0 CPU / 1GB RAM)
             └─► Gunicorn · W workers Uvicorn (procesos)
                   └─► POST /extract
                         1. Parseo multipart async → bytes en memoria (no bloquea loop por red)
                         2. SHA-256 de bytes ORIGINALES (barato, ~ms)
                         3. Semáforo de admisión (N=1–2 por proceso, timeout corto)
                             └─ saturado → 503 controlado {code, message}
                         4. Extracción PyMuPDF (CPU-bound, aislado en el proceso)
                         5. 200 {filename, extracted_text, checksum}

### 2.2 Reglas de saturación

- **Cola acotada (fail-fast):** `limit_concurrency` y backlog acotado en Gunicorn/Uvicorn. Mejor rechazar rápido que acumular latencia → evita timeouts en cascada desde API.
- **Backpressure con 503 (recomendado):** según `common.md` §2, 5xx = fallo atribuible al servicio/recurso. La saturación es un 5xx legítimo. Se responde **503** con envelope contractual `{code, message}` y header `Retry-After`. (El TP admite 429; se evalúa como alternativa, pero 429 es semántica de rate-limit por consumidor y no figura en el catálogo C1.)
- **Invariante R3 bajo carga:** PDF corrupto SIEMPRE responde 422, incluso saturado. El backpressure es una capa previa al procesamiento, nunca re-clasifica errores de dominio.
- **Límite defensivo de tamaño** (decisión de implementación, no contractual): rechazar bodies > umbral (p. ej. 64–100 MB) antes de cargarlos completos, protegiendo el 1GB de RAM. El límite contractual de 50 MB vive en API (borde).

### 2.3 Sin estado externo

No hay colas externas ni workers remotos: el backpressure se resuelve **in-process**. Coherente con B1 (cero llamadas salientes).

---

## 3. Fronteras del Bounded Context — Revalidación

| Decisión arquitectónica | Veredicto |
|---|---|
| **B1** — No llama a Persistence ni a ningún servicio; cero dependencias salientes | ✅ Confirmado |
| **B2** — Calcula SHA-256 sobre los bytes originales recibidos, sin transformación | ✅ Confirmado (equivalente a `checksum.py` actual) |
| **B3** — Entrada `multipart/form-data`, campo `file` | ✅ Confirmado |
| **R3** — Clasifica 400/422 (input) vs 500 (interno) antes de responder; nunca se confunden | ✅ Confirmado |
| Stateless puro: ningún resultado sobrevive a la respuesta, sin disco, sin caché | ✅ Confirmado |
| No conoce MongoDB, no conoce contratos de otros servicios | ✅ Confirmado |
| Salida exacta: `{filename, extracted_text, checksum}` (C1) | ✅ Confirmado |
| No se expone a internet (solo red interna, consumido por API) | ✅ Confirmado |

**Discrepancia detectada TP vs C1:** el TP pide `{"content", "page_count"}` con nota de "alinear con C1". Resolución propuesta: **C1 (spec congelada) manda** — no se agregan campos ni se renombra `extracted_text` en v1. Si la evaluación del TP lo exige, se resuelve como extensión explícita posterior, no como cambio silencioso del contrato.

**Pendiente no bloqueante:** ruta exacta de liveness (Master Plan §13.1, PROPUESTO `GET /health`). Se implementa liveness mínimo provisional sin dependencias.

---

## 4. Alcance explícito

**Hace:** recibir PDF por multipart, extraer texto completo, calcular SHA-256 de bytes originales, devolver contrato C1, clasificar errores, mantenerse stateless.

**No hace (no negociable):** persistir, acceder a Mongo, llamar a otros servicios, validar reglas de negocio (unicidad, límites de filename), exponerse a internet, orquestar el flujo.

## 5. Criterios de éxito (TP)

- k6 abierto: sostener ≥ 25 req/s, error rate < 1%.
- k6 spike: 100 VUs súbitos sin crash; rechazos 503 controlados y contabilizables.
- Vegeta: 50 req/s × 30s completado.
- Docker: `cpus: 1.0`, `memory: 1g` por réplica; hasta 5 réplicas detrás de Traefik/Caddy.
- RSS estable (sin fuga) bajo carga sostenida.