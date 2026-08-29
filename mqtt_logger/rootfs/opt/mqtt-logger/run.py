#!/usr/bin/env python3
"""MQTT Logger service entrypoint.

Subscribes to ``#`` on the local broker, drops the built-in noise prefixes
and any user ``filter_regex`` match, derives device/type/topic/format labels,
and ships every remaining message to Loki via a buffered background writer.
Also flushes rolling stats every 60s and routes push failures to an error
stream - same three Loki streams the old Node-RED flow produced
(``source="mqtt"``, and ``source="mqtt-logger"`` with ``type="stats"`` /
``type="error"``).
"""

from __future__ import annotations

import logging
import signal
import sys
import time

import paho.mqtt.client as mqtt

import config
import pipeline
from loki import LokiWriter
from stats import Stats, StatsFlusher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("mqtt_logger")


def main() -> int:
    cfg = config.load()
    user_patterns = pipeline.compile_user_patterns(cfg.filter_regex)
    log.info(
        "starting: broker=%s:%s loki=%s filter_patterns=%d auth=%s",
        cfg.mqtt_host,
        cfg.mqtt_port,
        cfg.loki_url,
        len(user_patterns),
        "yes" if cfg.has_credentials else "anonymous",
    )

    writer = LokiWriter(cfg.loki_url)
    writer.start()
    stats = Stats()
    flusher = StatsFlusher(stats, writer)
    flusher.start()

    forwarded = 0

    def on_connect(client, userdata, connect_flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("broker refused the connection: %s", reason_code)
            return
        client.subscribe("#", qos=0)
        log.info("connected to %s:%s, subscribed to #", cfg.mqtt_host, cfg.mqtt_port)

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        log.warning("disconnected from broker (%s); paho will reconnect", reason_code)

    def on_message(client, userdata, msg):
        nonlocal forwarded
        try:
            payload = msg.payload or b""
            if pipeline.should_drop(msg.topic, payload, user_patterns):
                return
            text = payload.decode("utf-8", "replace")
            labels = pipeline.extract_labels(msg.topic, pipeline.detect_format(text))
            writer.enqueue(labels, time.time_ns(), text)
            stats.record(labels)
            forwarded += 1
            if forwarded == 1 or forwarded % 1000 == 0:
                log.info(
                    "forwarded %d message(s) so far (queue=%d)",
                    forwarded,
                    writer.pending(),
                )
        except Exception:
            log.exception("failed to handle a message on %r", getattr(msg, "topic", "?"))

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=config.MQTT_CLIENT_ID,
        clean_session=True,
    )
    if cfg.has_credentials:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    def shutdown(signum, _frame):
        log.info("signal %s received, disconnecting", signum)
        client.disconnect()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
    except OSError as exc:
        log.warning("initial broker connect failed (%s); loop will retry", exc)

    rc = client.loop_forever(retry_first_connection=True)
    log.warning("MQTT loop exited (rc=%s); shutting down", rc)

    flusher.stop()
    writer.stop()
    return 0 if rc == mqtt.MQTTErrorCode.MQTT_ERR_SUCCESS else 1


if __name__ == "__main__":
    sys.exit(main())
