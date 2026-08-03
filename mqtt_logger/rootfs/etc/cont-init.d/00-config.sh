#!/usr/bin/with-contenv bashio
# Renders add-on options into the files/env vars the three services need,
# before any of them start. Re-runs on every container start, so changing
# an option and restarting the app is enough to apply it.

set -e

OPTIONS=/data/options.json

# --- MQTT credentials -> container-wide env vars, read by the Node-RED
# flow's broker config node via ${MQTT_USER}/${MQTT_PASSWORD} substitution.
MQTT_USER="$(jq --raw-output '.mqtt_username // ""' "${OPTIONS}")"
MQTT_PASSWORD="$(jq --raw-output '.mqtt_password // ""' "${OPTIONS}")"
mkdir -p /run/s6/container_environment
printf '%s' "${MQTT_USER}" > /run/s6/container_environment/MQTT_USER
printf '%s' "${MQTT_PASSWORD}" > /run/s6/container_environment/MQTT_PASSWORD

# --- Filter patterns -> a single JSON array env var, parsed once by the
# flow's filter Function node.
FILTER_REGEX_JSON="$(jq --compact-output '.filter_regex // []' "${OPTIONS}")"
printf '%s' "${FILTER_REGEX_JSON}" > /run/s6/container_environment/FILTER_REGEX_JSON

# --- Retention -> Loki config, rendered from the shipped template into the
# persistent /data volume (never edit the template in place; it's reread on
# every start).
RETENTION_DAYS="$(jq --raw-output '.retention_days // 30' "${OPTIONS}")"
RETENTION_HOURS="$((RETENTION_DAYS * 24))"
mkdir -p /data/loki
sed "s/__RETENTION_HOURS__/${RETENTION_HOURS}/g" \
    /etc/loki/local-config.yaml.tmpl > /data/loki/config.yaml

bashio::log.info "Configured: retention=${RETENTION_DAYS}d, $(jq 'length' <<< "${FILTER_REGEX_JSON}") filter pattern(s)"
