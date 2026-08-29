#!/usr/bin/with-contenv bashio
# Renders the one add-on option that needs baking into a config file (Loki's
# retention) before the services start, and cleans up state left by the
# pre-1.1.0 Node-RED implementation. Re-runs on every container start, so
# changing retention and restarting the app is enough to apply it.
#
# MQTT credentials and filter_regex are NOT handled here anymore - the MQTT
# Logger service reads /data/options.json directly.

set -e

OPTIONS=/data/options.json

# --- Retention -> Loki config, rendered from the shipped template into the
# persistent /data volume (never edit the template in place; it's reread on
# every start).
RETENTION_DAYS="$(jq --raw-output '.retention_days // 180' "${OPTIONS}")"
RETENTION_HOURS="$((RETENTION_DAYS * 24))"
mkdir -p /data/loki
sed "s/__RETENTION_HOURS__/${RETENTION_HOURS}/g" \
    /etc/loki/local-config.yaml.tmpl > /data/loki/config.yaml

# --- One-time cleanup for installs upgraded from <= 1.0.9: Node-RED's data
# dir (flows.json, credentials, settings) is dead weight now. Loki's and
# Grafana's data dirs are untouched, so message history carries over.
if [[ -d /data/nodered ]]; then
    rm -rf /data/nodered
    bashio::log.info "Removed leftover /data/nodered from the pre-1.1.0 Node-RED setup"
fi

FILTER_COUNT="$(jq '(.filter_regex // []) | length' "${OPTIONS}")"
bashio::log.info "Configured: retention=${RETENTION_DAYS}d, ${FILTER_COUNT} filter pattern(s)"
