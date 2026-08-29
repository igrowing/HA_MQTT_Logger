"""End-to-end checks against the real add-on image.

Requires the compose stack from docker-compose.test.yml to be up. Each test
uses a unique topic prefix so reruns against a warm Loki don't collide.
"""

import json
import time

import pytest

from helpers import Loki, compose


def test_real_and_noise_messages(publisher, loki, prefix):
    publisher(f"{prefix}/kitchen/state", json.dumps({"temp": 21.4}))
    publisher(f"{prefix}/porch/availability", "online")
    # noise: each built-in prefix + the user filter_regex pattern
    publisher("homeassistant/sensor/x/config", json.dumps({"n": prefix}))
    publisher("$SYS/broker/load", "1")
    publisher("discovery/thing", prefix)
    publisher("tasmota/discovery/AABBCC/config", prefix)
    publisher(f"{prefix}/thermostat/set", "dropme-by-user-pattern please")

    entries = Loki.wait_for(
        f'{{source="mqtt"}} |= "{prefix}"',
        lambda e: len(e) >= 2,
        timeout=30,
    )
    by_topic = {s["topic"]: (s, line) for s, ts, line in entries}

    assert set(by_topic) == {f"{prefix}/kitchen/state", f"{prefix}/porch/availability"}

    kitchen_labels, kitchen_line = by_topic[f"{prefix}/kitchen/state"]
    assert kitchen_labels["device"] == prefix
    assert kitchen_labels["type"] == "state"
    assert kitchen_labels["format"] == "json"
    assert json.loads(kitchen_line) == {"temp": 21.4}

    porch_labels, _ = by_topic[f"{prefix}/porch/availability"]
    assert porch_labels["type"] == "availability"
    assert porch_labels["format"] == "text"

    # nothing from the noise topics or the user-filtered message leaked in
    time.sleep(2)
    all_for_prefix = Loki.query_range(f'{{source="mqtt"}} |= "{prefix}"')
    assert len(all_for_prefix) == 2


def test_tasmota_topic_labelling(publisher, loki, prefix):
    publisher(f"stat/{prefix}_plug/POWER", "ON")
    entries = Loki.wait_for(
        f'{{source="mqtt", type="POWER"}} |= "{prefix}"',
        lambda e: len(e) >= 1,
    )
    labels = entries[0][0]
    assert labels["device"] == f"{prefix}_plug"


def test_burst_no_loss_while_healthy(publisher, loki, prefix):
    n = 3000
    for i in range(n):
        publisher(f"{prefix}/burst/msg", str(i), qos=1)

    entries = Loki.wait_for(
        f'{{source="mqtt", topic="{prefix}/burst/msg"}}',
        lambda e: len(e) >= n,
        timeout=60,
    )
    seen = {int(line) for _s, _ts, line in entries}
    assert seen == set(range(n))


def test_stats_stream_flushes(publisher, loki, prefix):
    publisher(f"{prefix}/stats/probe", "1")
    entries = Loki.wait_for(
        '{source="mqtt-logger", type="stats"}',
        lambda e: any(json.loads(l).get("total", 0) > 0 for _s, _t, l in e),
        timeout=75,
    )
    latest = json.loads(entries[-1][2])
    assert set(latest) == {"total", "byDevice", "byType", "byFormat"}


@pytest.mark.slow
def test_recovery_after_loki_outage(publisher, loki, prefix):
    """Pause Loki, publish past the queue cap, unpause; expect a drop report."""
    compose("pause", "loki")
    try:
        # QUEUE_MAX is 20000; overshoot so drop-oldest definitely triggers
        for i in range(26000):
            publisher(f"{prefix}/outage/msg", str(i), qos=0)
        time.sleep(3)
    finally:
        compose("unpause", "loki")

    err = Loki.wait_for(
        '{source="mqtt-logger", type="error"}',
        lambda e: any("while Loki was unreachable" in l for _s, _t, l in e),
        timeout=60,
    )
    msg = [l for _s, _t, l in err if "while Loki was unreachable" in l][-1]
    dropped = int(json.loads(msg)["message"].split()[1])
    assert dropped > 0

    # the messages that did survive the outage still made it through
    survived = Loki.count(f'{{source="mqtt", topic="{prefix}/outage/msg"}}', limit=30000)
    assert survived > 0
    assert survived + dropped <= 26000
