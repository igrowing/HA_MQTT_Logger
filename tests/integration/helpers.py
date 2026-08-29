"""Shared helpers for the integration tests (host-side, talks to the
published ports from docker-compose.test.yml)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import requests

COMPOSE_FILE = str(Path(__file__).parent / "docker-compose.test.yml")

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "18883"))
LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:13100").rstrip("/")


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, *args],
        check=check,
        capture_output=True,
        text=True,
    )


class Loki:
    @staticmethod
    def query_range(logql: str, since_seconds: int = 900, limit: int = 30000):
        end = time.time_ns()
        start = end - since_seconds * 1_000_000_000
        resp = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={"query": logql, "start": start, "end": end, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        entries = []
        for stream in resp.json()["data"]["result"]:
            for ts, line in stream["values"]:
                entries.append((stream["stream"], ts, line))
        return entries

    @classmethod
    def count(cls, logql: str, **kw) -> int:
        return len(cls.query_range(logql, **kw))

    @classmethod
    def wait_for(cls, logql: str, predicate, timeout: float = 30.0, interval: float = 1.0):
        deadline = time.monotonic() + timeout
        last = []
        while time.monotonic() < deadline:
            last = cls.query_range(logql)
            if predicate(last):
                return last
            time.sleep(interval)
        raise AssertionError(
            f"condition not met within {timeout}s for {logql!r}; last {len(last)} entries"
        )
