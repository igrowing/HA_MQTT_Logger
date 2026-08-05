# syntax=docker/dockerfile:1
#
# Grafana and Loki are pulled pre-built from their own official Alpine/musl
# images (same libc family as the Home Assistant base image) and copied in,
# rather than hand-fetched by URL - this makes multi-arch resolution
# automatic under `docker buildx --platform ...` instead of hand-mapping
# TARGETARCH to release asset names. Node-RED is installed via npm directly,
# same as the official Home Assistant Node-RED add-on does it.
#
# GRAFANA_VERSION / LOKI_VERSION / NODERED_VERSION to current stable releases.
#
# All ARGs used in a FROM line must be declared before the FIRST FROM in the
# file to stay in global scope - an ARG declared between two FROM lines only
# belongs to the stage above it, so BUILD_FROM has to live up here too, not
# just before the stage that consumes it.
ARG GRAFANA_VERSION=13.0.2
ARG LOKI_VERSION=3.7.4
ARG NODERED_VERSION=5.0.4
ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23

FROM grafana/grafana-oss:${GRAFANA_VERSION} AS grafana
FROM grafana/loki:${LOKI_VERSION} AS loki

FROM ${BUILD_FROM}
ARG NODERED_VERSION

# Grafana: binary + conf + public assets, self-contained under /usr/share/grafana
COPY --from=grafana /usr/share/grafana /usr/share/grafana
RUN ln -s /usr/share/grafana/bin/grafana /usr/bin/grafana

# Loki: single static-ish binary
COPY --from=loki /usr/bin/loki /usr/bin/loki

# Node-RED, installed for whichever arch this build runs under (buildx
# resolves nodejs/npm from Alpine's own multi-arch package repo).
RUN apk add --no-cache nodejs npm jq \
    && npm install --global --omit=dev --no-audit --no-fund node-red@${NODERED_VERSION} \
    && npm cache clean --force

# Static config: Grafana provisioning + dashboard, Loki config template,
# seed Node-RED flow. Values that depend on add-on options are rendered by
# rootfs/etc/cont-init.d/00-config.sh at container start, not at build time.
COPY rootfs /

# Grafana always scans these provisioning subdirs even though this add-on
# only ships dashboards/datasources - without them it logs a startup error
# for each ("no such file or directory") on every boot.
RUN mkdir -p /etc/grafana/provisioning/plugins /etc/grafana/provisioning/alerting

# Resolve the dashboard's Grafana-import-time datasource placeholder to the
# fixed datasource uid provisioned in etc/grafana/provisioning/datasources -
# file-based dashboard provisioning has no "pick a datasource" prompt like a
# manual import does, so this has to already be a concrete uid.
RUN sed -i 's/\${DS_LOKI}/loki/g' /etc/grafana/dashboards/mqtt_devices.json \
    && jq 'del(.__inputs, .__requires)' /etc/grafana/dashboards/mqtt_devices.json \
        > /etc/grafana/dashboards/mqtt_devices.json.tmp \
    && mv /etc/grafana/dashboards/mqtt_devices.json.tmp /etc/grafana/dashboards/mqtt_devices.json

LABEL \
    org.opencontainers.image.title="MQTT Logger" \
    org.opencontainers.image.description="Logs every MQTT message to Loki and browses it in a built-in Grafana dashboard" \
    org.opencontainers.image.source="https://github.com/igrowing/HA_MQTT_Logger" \
    org.opencontainers.image.licenses="MIT"
