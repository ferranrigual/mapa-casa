#!/usr/bin/env bash
# Ejecuta un comando dentro del contenedor mapa-casa con acceso a la GPU.
# La carpeta del proyecto se monta en /work.
#   ./scripts/run.sh colmap help
#   ./scripts/run.sh                 (shell interactiva)
#   PORT=8080 ./scripts/run.sh ...   (publica ese puerto, p.ej. para el visor)
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
args=(--rm --device nvidia.com/gpu=all --security-opt=label=disable --shm-size=8g
      -e NVIDIA_DISABLE_REQUIRE=1 -v "$PROJECT_DIR":/work)
[ -t 0 ] && [ -t 1 ] && args+=(-it)
[ -n "${PORT:-}" ] && args+=(-p "$PORT:$PORT")
[ $# -eq 0 ] && set -- bash
exec podman run --entrypoint "" "${args[@]}" localhost/mapa-casa:latest "$@"
