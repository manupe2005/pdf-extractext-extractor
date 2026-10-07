#!/bin/bash
# tests/load/profile.sh — Muestreo de CPU/RSS/restarts del contenedor de extracción (Issue #9).
#
# Uso:
#   tests/load/profile.sh start <run_id>   # inicia muestreo en segundo plano
#   tests/load/profile.sh stop             # detiene el muestreo
#   tests/load/profile.sh finish <run_id>  # anota RSS de reposo y restarts finales
#   tests/load/profile.sh summary <run_id> # resume el CSV del run
#
# Artefactos por run: tests/load/results/<run_id>.stats.csv y .meta.txt

set -u

RESULTS_DIR="tests/load/results"
CONTAINER_PATTERN="pdf-extractext-extraction"
PIDFILE="$RESULTS_DIR/.profile.pid"
INTERVAL=1

mkdir -p "$RESULTS_DIR"

containers() {
    docker ps --filter "name=${CONTAINER_PATTERN}" --format '{{.Names}}'
}

# RSS agregado en MiB de todos los contenedores de extracción.
total_rss_mib() {
    docker stats --no-stream --format '{{.MemUsage}}' $(containers) \
        | awk '{v=$1; sub(/[A-Za-z]+$/,"",v); u=$1; gsub(/[0-9.]/,"",u);
                f=(u=="GiB"?1024:(u=="KiB"?1/1024:1)); s+=v*f} END {printf "%.1f", s}'
}

# Imprime restarts totales en stdout y detalle por contenedor al meta ($1 o /dev/stderr).
restarts_total() {
    local total=0 n oom
    for c in $(containers); do
        n=$(docker inspect -f '{{.RestartCount}}' "$c")
        oom=$(docker inspect -f '{{.State.OOMKilled}}' "$c")
        total=$((total + n))
        echo "$c restarts=$n oom=$oom" >> "$1"
    done
    echo "$total"
}

case "${1:-}" in
    start)
        run_id="${2:?Falta run_id}"
        csv="$RESULTS_DIR/${run_id}.stats.csv"
        meta="$RESULTS_DIR/${run_id}.meta.txt"
        echo "timestamp,container,cpu_perc,mem_mib,pids" > "$csv"
        {
            echo "run_id=$run_id"
            echo "started_at=$(date -Iseconds)"
            echo "containers: $(containers | tr '\n' ' ')"
            echo "restarts_initial=$(restarts_total /dev/stdout)"
            echo "rss_initial_mib=$(total_rss_mib)"
        } > "$meta"

        (
            while true; do
                ts=$(date -Iseconds)
                docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}' $(containers) \
                | awk -F'|' -v ts="$ts" '{
                    cpu=$2; gsub(/%/,"",cpu);
                    split($3,a," "); v=a[1]; sub(/[A-Za-z]+$/,"",v);
                    u=a[1]; gsub(/[0-9.]/,"",u);
                    f=(u=="GiB"?1024:(u=="KiB"?1/1024:1));
                    printf "%s,%s,%s,%.1f,%s\n", ts, $1, cpu, v*f, $4;
                }' >> "$csv"
                sleep "$INTERVAL"
            done
        ) &
        echo $! > "$PIDFILE"
        echo "Profiling iniciado: $csv (pid $(cat $PIDFILE))"
        ;;
    stop)
        if [ -f "$PIDFILE" ]; then
            kill "$(cat $PIDFILE)" 2>/dev/null
            rm -f "$PIDFILE"
            echo "Profiling detenido."
        else
            echo "No hay muestreo activo."
        fi
        ;;
    finish)
        run_id="${2:?Falta run_id}"
        meta="$RESULTS_DIR/${run_id}.meta.txt"
        {
            echo "rss_final_mib=$(total_rss_mib)"
            echo "restarts_final=$(restarts_total /dev/stdout)"
            echo "finished_at=$(date -Iseconds)"
        } >> "$meta"
        echo "Meta finalizado: $meta"
        ;;
    summary)
        run_id="${2:?Falta run_id}"
        csv="$RESULTS_DIR/${run_id}.stats.csv"
        echo "=== Resumen $run_id ==="
        cat "$RESULTS_DIR/${run_id}.meta.txt"
        echo "--- Muestras: $(awk 'END{print NR-1}' "$csv") ---"
        awk -F',' 'NR>1 {
            cpu+=$3; mem+=$4; n++;
            if ($3+0>cpumax) cpumax=$3+0;
            if ($4+0>memmax) memmax=$4+0;
        } END {
            if (n>0) {
                printf "CPU promedio: %.1f%%  |  CPU max: %.1f%%\n", cpu/n, cpumax;
                printf "RSS promedio: %.1f MiB  |  RSS max: %.1f MiB\n", mem/n, memmax;
            }
        }' "$csv"
        ;;
    *)
        echo "Uso: $0 {start|stop|finish|summary} [run_id]" >&2
        exit 1
        ;;
esac
