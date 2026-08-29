"""Runtime configuration for the MQTT Logger service.

Everything the service needs to start is derived here: the MQTT broker
coordinates and credentials, the Loki push URL, and the user's filter
patterns. Add-on options come straight from ``/data/options.json`` (written
by the Supervisor from the app's Configuration tab) - there is no env-var
dance in cont-init anymore.

Every value has a production default and an env override. The overrides exist
for the docker-compose integration harness, which points the service at a
throwaway broker/Loki; a real install sets none of them.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("mqtt_logger.config")

# Fixed in a Home Assistant install: the Mosquitto add-on is always reachable
# as core-mosquitto:1883, and this is the client id the app has used since
# 1.0.3 (see DOCS troubleshooting for the id-collision story).
DEFAULT_MQTT_HOST = "core-mosquitto"
DEFAULT_MQTT_PORT = 1883
MQTT_CLIENT_ID = "ha-mqtt-logger-addon"

# Loki runs in this same container.
DEFAULT_LOKI_URL = "http://localhost:3100/loki/api/v1/push"

DEFAULT_OPTIONS_FILE = "/data/options.json"


@dataclass
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    loki_url: str
    filter_regex: list[str] = field(default_factory=list)

    @property
    def has_credentials(self) -> bool:
        return bool(self.mqtt_username)


def _load_options(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            log.warning("%s is not a JSON object, ignoring it", path)
            return {}
        return data
    except FileNotFoundError:
        # Running outside the add-on (tests, local dev) - fine, fall back to
        # env / defaults.
        log.info("no options file at %s, using defaults", path)
        return {}
    except (OSError, ValueError) as exc:
        log.warning("could not read %s (%s), using defaults", path, exc)
        return {}


def load() -> Config:
    options_file = os.environ.get("OPTIONS_FILE", DEFAULT_OPTIONS_FILE)
    options = _load_options(options_file)

    filter_regex = options.get("filter_regex") or []
    if not isinstance(filter_regex, list):
        log.warning("filter_regex in %s is not a list, ignoring it", options_file)
        filter_regex = []

    return Config(
        mqtt_host=os.environ.get("MQTT_HOST", DEFAULT_MQTT_HOST),
        mqtt_port=int(os.environ.get("MQTT_PORT", DEFAULT_MQTT_PORT)),
        mqtt_username=os.environ.get("MQTT_USER", options.get("mqtt_username", "") or ""),
        mqtt_password=os.environ.get(
            "MQTT_PASSWORD", options.get("mqtt_password", "") or ""
        ),
        loki_url=os.environ.get("LOKI_URL", DEFAULT_LOKI_URL),
        filter_regex=[str(p) for p in filter_regex],
    )
