"""Fixtures for the docker-compose integration tests.

Bring the stack up first:

    docker compose -f tests/integration/docker-compose.test.yml up -d --build
    ./tests/integration/wait-for-ready.sh
"""

from __future__ import annotations

import uuid

import paho.mqtt.client as mqtt
import pytest

from helpers import MQTT_HOST, MQTT_PORT, Loki


@pytest.fixture(scope="session")
def publisher():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=f"itest-pub-{uuid.uuid4().hex[:8]}"
    )
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    def publish(topic: str, payload: str, qos: int = 0):
        client.publish(topic, payload, qos=qos).wait_for_publish(timeout=5)

    yield publish
    client.loop_stop()
    client.disconnect()


@pytest.fixture(scope="session")
def loki():
    return Loki


@pytest.fixture
def prefix():
    return f"itest-{uuid.uuid4().hex[:10]}"
