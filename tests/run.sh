#!/usr/bin/env bash
# Convenience wrapper for the two test layers.
#
#   tests/run.sh unit          # fast, pure-Python, no Docker
#   tests/run.sh integration   # builds the image, runs the compose stack
#   tests/run.sh all
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "${here}/.." && pwd)"
compose_file="${here}/integration/docker-compose.test.yml"

run_unit() {
    python -m pytest -q "${repo}/tests/unit"
}

run_integration() {
    docker compose -f "${compose_file}" up -d --build
    trap 'docker compose -f "${compose_file}" down -v' EXIT
    "${here}/integration/wait-for-ready.sh"
    python -m pytest -q "${repo}/tests/integration"
}

case "${1:-all}" in
    unit) run_unit ;;
    integration) run_integration ;;
    all) run_unit && run_integration ;;
    *) echo "usage: $0 [unit|integration|all]" >&2; exit 2 ;;
esac
