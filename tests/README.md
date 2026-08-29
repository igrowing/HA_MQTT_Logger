# Tests

The MQTT Logger service lives at
[`mqtt_logger/rootfs/opt/mqtt-logger/`](../mqtt_logger/rootfs/opt/mqtt-logger)
(in-container path `/opt/mqtt-logger`). None of the test tooling ships in the
add-on image.

## Unit tests — `tests/unit/`

Pure-Python, no broker, no Loki, no Docker. They cover the filter / label /
format logic, the batching + retry/backoff + drop-oldest behaviour of the
Loki writer, the stats counters, and config loading.

```sh
pip install -r tests/requirements.txt
pytest              # picks up tests/unit via pytest.ini
```

## Integration tests — `tests/integration/`

Bring up a throwaway Mosquitto + Loki + the **real add-on image** (its s6
entrypoint bypassed so only the logger script runs — this also proves
`python3` + `py3-paho-mqtt` resolve on the HA base image), then publish MQTT
messages and assert what lands in Loki over its HTTP query API.

```sh
pip install -r tests/requirements.txt
tests/run.sh integration
# or manually:
docker compose -f tests/integration/docker-compose.test.yml up -d --build
tests/integration/wait-for-ready.sh
pytest tests/integration            # add -m "not slow" to skip the outage test
docker compose -f tests/integration/docker-compose.test.yml down -v
```

Covered: real vs. noise-topic filtering, Tasmota topic labelling, a
no-loss burst while Loki is healthy, the 60 s stats flush, and (marked
`slow`) dropping the oldest messages during a Loki outage with a recovery
report on the `type="error"` stream.

CI runs both layers in [`.github/workflows/tests.yaml`](../.github/workflows/tests.yaml).
