"""Buffered, retrying Loki push client.

Replaces the flow's "Build Loki payload" -> "http request" -> "Check
response" -> catch chain. ``on_message`` only ever calls :meth:`LokiWriter.
enqueue`, which is non-blocking; a single background thread batches whatever
has queued up and POSTs it to Loki, retrying with exponential backoff while
Loki is unreachable.

Backpressure: the queue is bounded (:data:`LokiWriter.QUEUE_MAX`). When it is
full - Loki down long enough for the buffer to fill - the oldest unsent
message is dropped to make room, favouring "what's happening now" freshness.
The drop count is reported to the error stream once Loki comes back.
"""

from __future__ import annotations

import collections
import json
import logging
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("mqtt_logger.loki")

Entry = tuple  # (labels: dict[str, str], ts_ns: int, line: str)


class LokiWriter:
    BATCH_MAX = 500          # values per POST
    FLUSH_INTERVAL = 0.5     # seconds to wait for a batch to fill
    QUEUE_MAX = 20000        # buffered messages before drop-oldest kicks in
    MIN_BACKOFF = 1.0
    MAX_BACKOFF = 30.0
    MAX_CLIENT_ERROR_TRIES = 3  # give up on a 4xx-rejected batch after this
    HTTP_TIMEOUT = 10.0

    def __init__(self, url: str, *, post=None, sleep=time.sleep, clock=time.time_ns):
        self._url = url
        self._post_fn = post or self._http_post
        self._sleep = sleep
        self._clock = clock
        self._dq: "collections.deque[Entry]" = collections.deque()
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._dropped = 0  # queue-overflow drops awaiting a recovery report
        self._thread = threading.Thread(
            target=self._run, name="loki-writer", daemon=True
        )

    # -- public API ------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def enqueue(self, labels: dict[str, str], ts_ns: int, line: str) -> None:
        with self._cv:
            if len(self._dq) >= self.QUEUE_MAX:
                self._dq.popleft()
                self._dropped += 1
            self._dq.append((labels, ts_ns, line))
            self._cv.notify()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        self._thread.join(timeout)
        self._final_flush()

    @property
    def dropped(self) -> int:
        return self._dropped

    def pending(self) -> int:
        with self._cv:
            return len(self._dq)

    # -- worker --------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                batch = self._collect()
                if batch:
                    self._send_with_retry(batch)
            except Exception:
                # Never let the writer thread die - that would silently stop
                # all Loki delivery while MQTT ingest keeps filling the queue.
                log.exception("loki-writer loop error; continuing")
                self._stop.wait(1.0)

    def _collect(self) -> list[Entry]:
        with self._cv:
            if not self._dq and not self._stop.is_set():
                self._cv.wait(timeout=self.FLUSH_INTERVAL)
            batch: list[Entry] = []
            while self._dq and len(batch) < self.BATCH_MAX:
                batch.append(self._dq.popleft())
            return batch

    def _send_with_retry(self, batch: list[Entry]) -> None:
        backoff = self.MIN_BACKOFF
        tries = 0
        while True:
            result = self._try_post(batch)
            if result == "ok":
                self._report_recovery_if_needed()
                return
            tries += 1
            if result == "fatal" and tries >= self.MAX_CLIENT_ERROR_TRIES:
                self._report_rejected_batch(batch)
                return
            if self._stop.is_set():
                # shutting down against a dead Loki: put the batch back so
                # _final_flush gets one last attempt, don't block on backoff.
                with self._cv:
                    self._dq.extendleft(reversed(batch))
                return
            self._sleep(backoff)
            backoff = min(backoff * 2, self.MAX_BACKOFF)

    def _try_post(self, batch: list[Entry]) -> str:
        body = self._build_payload(batch)
        try:
            status = self._post_fn(self._url, body)
        except Exception as exc:  # network error, DNS, timeout, ...
            log.warning("Loki push failed (%s); will retry", exc)
            return "retriable"
        if 200 <= status < 300:
            return "ok"
        if status == 429 or status >= 500:
            log.warning("Loki push got HTTP %s; will retry", status)
            return "retriable"
        log.error("Loki push got HTTP %s (client error)", status)
        return "fatal"

    # -- payload / reporting -----------------------------------------------

    @staticmethod
    def _build_payload(batch: list[Entry]) -> bytes:
        streams: dict[tuple, list[tuple[str, str]]] = {}
        for labels, ts_ns, line in batch:
            key = tuple(sorted(labels.items()))
            streams.setdefault(key, []).append((str(ts_ns), line))
        payload = {
            "streams": [
                {
                    "stream": dict(key),
                    "values": sorted(values, key=lambda v: int(v[0])),
                }
                for key, values in streams.items()
            ]
        }
        return json.dumps(payload).encode("utf-8")

    def _http_post(self, url: str, body: bytes) -> int:
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.HTTP_TIMEOUT) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def _emit_error(self, detail: dict, device: str = "mqtt-logger") -> None:
        self.enqueue(
            {"source": "mqtt-logger", "type": "error", "device": device},
            self._clock(),
            json.dumps(detail),
        )

    def _report_recovery_if_needed(self) -> None:
        with self._cv:
            n, self._dropped = self._dropped, 0
        if n:
            log.warning("Loki recovered; dropped %d messages during the outage", n)
            self._emit_error(
                {"message": f"dropped {n} messages while Loki was unreachable"}
            )

    def _report_rejected_batch(self, batch: list[Entry]) -> None:
        first_topic = batch[0][0].get("topic", "unknown") if batch else "unknown"
        log.error("Loki rejected a batch of %d messages; dropping it", len(batch))
        self._emit_error(
            {
                "message": f"Loki rejected a batch, dropped {len(batch)} messages",
                "topic": first_topic,
            }
        )

    def _final_flush(self) -> None:
        with self._cv:
            leftover = list(self._dq)
            self._dq.clear()
        if not leftover:
            return
        try:
            self._post_fn(self._url, self._build_payload(leftover))
        except Exception as exc:
            log.warning("final flush of %d messages failed (%s)", len(leftover), exc)
