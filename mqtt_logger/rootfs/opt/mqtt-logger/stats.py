"""Rolling ingest counters, flushed to Loki every 60s.

Ports the flow's "Update statistics" node + its 60s ``inject`` flush. The
JSON shape ({total, byDevice, byType, byFormat}) is unchanged so anything in
Grafana reading ``{source="mqtt-logger", type="stats"}`` keeps working.
Counters are cumulative since process start, exactly like the old
``flow.get('mqttStats')`` context was.
"""

from __future__ import annotations

import json
import logging
import threading
import time

log = logging.getLogger("mqtt_logger.stats")


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._by_device: dict[str, int] = {}
        self._by_type: dict[str, int] = {}
        self._by_format: dict[str, int] = {}

    def record(self, labels: dict[str, str]) -> None:
        with self._lock:
            self._total += 1
            for bucket, key in (
                (self._by_device, labels.get("device", "unknown")),
                (self._by_type, labels.get("type", "unknown")),
                (self._by_format, labels.get("format", "unknown")),
            ):
                bucket[key] = bucket.get(key, 0) + 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": self._total,
                "byDevice": dict(self._by_device),
                "byType": dict(self._by_type),
                "byFormat": dict(self._by_format),
            }


class StatsFlusher:
    INITIAL_DELAY = 5.0
    INTERVAL = 60.0

    def __init__(self, stats: Stats, writer, *, clock=time.time_ns):
        self._stats = stats
        self._writer = writer
        self._clock = clock
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="stats-flusher", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def flush_once(self) -> None:
        self._writer.enqueue(
            {"source": "mqtt-logger", "type": "stats"},
            self._clock(),
            json.dumps(self._stats.snapshot()),
        )

    def _run(self) -> None:
        if self._stop.wait(self.INITIAL_DELAY):
            return
        while not self._stop.is_set():
            self.flush_once()
            self._stop.wait(self.INTERVAL)
