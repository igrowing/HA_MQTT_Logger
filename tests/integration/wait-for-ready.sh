#!/usr/bin/env bash
# Block until Loki and the logger container are up, or fail after ~90s.
set -euo pipefail

COMPOSE=(docker compose -f "$(dirname "$0")/docker-compose.test.yml")
LOKI_URL="${LOKI_URL:-http://localhost:13100}"

echo "waiting for Loki at ${LOKI_URL}/ready ..."
for _ in $(seq 1 45); do
    if curl -fsS "${LOKI_URL}/ready" 2>/dev/null | grep -q ready; then
        echo "loki ready"
        break
    fi
    sleep 2
done

echo "waiting for the logger to connect to the broker ..."
for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" logs logger 2>&1 | grep -q "subscribed to #"; then
        echo "logger connected"
        exit 0
    fi
    sleep 2
done

echo "logger did not connect in time; recent logs:" >&2
"${COMPOSE[@]}" logs --tail 50 logger >&2
exit 1
