# syntax=docker/dockerfile:1
#
# Grafana and Loki are pulled pre-built from their own official Alpine/musl
# images (same libc family as the Home Assistant base image) and copied in,
# rather than hand-fetched by URL - this makes multi-arch resolution
# automatic under `docker buildx --platform ...` instead of hand-mapping
# TARGETARCH to release asset names. MQTT ingest/filter/forward is a small
# Python service (rootfs/opt/mqtt-logger), replacing the old Node-RED flow -
# python3 + py3-paho-mqtt is ~100-140 MB lighter per arch than nodejs + npm
# + a global node-red install.
#
# GRAFANA_VERSION / LOKI_VERSION pin the copied-in binaries to current stable
# releases.
#
# All ARGs used in a FROM line must be declared before the FIRST FROM in the
# file to stay in global scope - an ARG declared between two FROM lines only
# belongs to the stage above it, so BUILD_FROM has to live up here too, not
# just before the stage that consumes it.
ARG GRAFANA_VERSION=13.0.2
ARG LOKI_VERSION=3.7.4
ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23

FROM grafana/grafana-oss:${GRAFANA_VERSION} AS grafana
FROM grafana/loki:${LOKI_VERSION} AS loki

FROM ${BUILD_FROM}

# Grafana: binary + conf + public assets, self-contained under /usr/share/grafana
COPY --from=grafana /usr/share/grafana /usr/share/grafana
RUN ln -s /usr/share/grafana/bin/grafana /usr/bin/grafana

# Loki: single static-ish binary
COPY --from=loki /usr/bin/loki /usr/bin/loki

# MQTT Logger service runtime. Alpine's own multi-arch package repo carries
# py3-paho-mqtt, but pinned at 1.6.1 even on edge - well short of the 2.x
# CallbackAPIVersion API this service is written against - so paho-mqtt has
# to come from pip instead. jq stays for cont-init and the dashboard-rewrite
# step below.
RUN apk add --no-cache python3 py3-pip jq \
    && pip install --no-cache-dir --break-system-packages "paho-mqtt>=2,<3"
ENV PYTHONUNBUFFERED=1

# Static config: Grafana provisioning + dashboard, Loki config template, and
# the MQTT Logger service under /opt/mqtt-logger. Values that depend on
# add-on options are read at runtime (the service reads /data/options.json
# directly; Loki's retention is rendered by
# rootfs/etc/cont-init.d/00-config.sh at container start).
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
