import json
import threading
import time

import pytest

from loki import LokiWriter


class FakePost:
    """Records POST bodies; scriptable status codes / exceptions."""

    def __init__(self, results=None):
        # results: list of int status codes or Exception instances, consumed
        # in order; the last one repeats once exhausted.
        self._results = list(results or [204])
        self.calls = []  # list of decoded payload dicts
        self.lock = threading.Lock()

    def __call__(self, url, body):
        with self.lock:
            self.calls.append(json.loads(body.decode("utf-8")))
            result = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        if isinstance(result, Exception):
            raise result
        return result


def make_writer(**kw):
    post = kw.pop("post", FakePost())
    sleeps = []
    w = LokiWriter(
        "http://loki.test/push",
        post=post,
        sleep=lambda s: sleeps.append(s),
        clock=lambda: 1_700_000_000_000_000_000,
    )
    for k, v in kw.items():
        setattr(w, k, v)
    return w, post, sleeps


class TestBuildPayload:
    def test_groups_values_by_label_set(self):
        a = {"source": "mqtt", "device": "d1", "type": "state"}
        b = {"source": "mqtt", "device": "d2", "type": "state"}
        batch = [(a, 3, "x"), (b, 1, "y"), (a, 2, "z")]
        payload = json.loads(LokiWriter._build_payload(batch))
        streams = {frozenset(s["stream"].items()): s["values"] for s in payload["streams"]}
        assert len(streams) == 2
        # a's two values, sorted by ts ascending
        assert streams[frozenset(a.items())] == [["2", "z"], ["3", "x"]]
        assert streams[frozenset(b.items())] == [["1", "y"]]

    def test_timestamp_is_stringified_nanoseconds(self):
        payload = json.loads(LokiWriter._build_payload([({"a": "b"}, 1_700_000_000_123_456_789, "l")]))
        ts = payload["streams"][0]["values"][0][0]
        assert ts == "1700000000123456789"
        assert len(ts) == 19


class TestEnqueueOverflow:
    def test_drops_oldest_and_counts(self):
        w, _post, _ = make_writer(QUEUE_MAX=3)
        for i in range(5):
            w.enqueue({"topic": "t"}, i, f"line{i}")
        assert w.pending() == 3
        assert w.dropped == 2
        remaining = [line for (_lbl, _ts, line) in list(w._dq)]
        assert remaining == ["line2", "line3", "line4"]


class TestTryPostClassification:
    @pytest.mark.parametrize(
        "result,expected",
        [
            (204, "ok"),
            (200, "ok"),
            (500, "retriable"),
            (503, "retriable"),
            (429, "retriable"),
            (400, "fatal"),
            (413, "fatal"),
            (ConnectionError("boom"), "retriable"),
        ],
    )
    def test_classification(self, result, expected):
        w, _post, _ = make_writer(post=FakePost([result]))
        assert w._try_post([({"topic": "t"}, 1, "l")]) == expected


class TestSendWithRetry:
    def test_retries_with_exponential_backoff_then_succeeds(self):
        post = FakePost([ConnectionError("x"), ConnectionError("x"), ConnectionError("x"), 204])
        w, _post, sleeps = make_writer(post=post, MIN_BACKOFF=1, MAX_BACKOFF=30)
        w._send_with_retry([({"source": "mqtt", "topic": "t"}, 1, "l")])
        assert sleeps == [1, 2, 4]
        assert len(post.calls) == 4

    def test_backoff_is_capped(self):
        post = FakePost([500, 500, 500, 500, 500, 500, 204])
        w, _post, sleeps = make_writer(post=post, MIN_BACKOFF=1, MAX_BACKOFF=8)
        w._send_with_retry([({"topic": "t"}, 1, "l")])
        assert sleeps == [1, 2, 4, 8, 8, 8]

    def test_persistent_client_error_drops_batch_and_reports(self):
        w, _post, sleeps = make_writer(post=FakePost([400]), MAX_CLIENT_ERROR_TRIES=3)
        batch = [({"source": "mqtt", "topic": "sensors/leak"}, 1, "l")] * 4
        w._send_with_retry(batch)
        # one error line was enqueued for the operator
        assert w.pending() == 1
        labels, _ts, line = w._dq[0]
        assert labels == {"source": "mqtt-logger", "type": "error", "device": "mqtt-logger"}
        detail = json.loads(line)
        assert detail["message"] == "Loki rejected a batch, dropped 4 messages"
        assert detail["topic"] == "sensors/leak"


class TestRecoveryReport:
    def test_emits_summary_line_after_drops(self):
        w, _post, _ = make_writer()
        w._dropped = 7
        w._report_recovery_if_needed()
        assert w.dropped == 0
        labels, _ts, line = w._dq[0]
        assert labels["type"] == "error"
        assert json.loads(line) == {"message": "dropped 7 messages while Loki was unreachable"}

    def test_no_line_when_nothing_dropped(self):
        w, _post, _ = make_writer()
        w._report_recovery_if_needed()
        assert w.pending() == 0


class TestThreadedRun:
    def test_enqueued_messages_reach_loki(self):
        w, post, _ = make_writer(FLUSH_INTERVAL=0.05)
        w.start()
        try:
            for i in range(10):
                w.enqueue({"source": "mqtt", "device": "d", "type": "t", "topic": "d/t"}, i, f"m{i}")
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                lines = [v[1] for c in post.calls for s in c["streams"] for v in s["values"]]
                if len(lines) >= 10:
                    break
                time.sleep(0.02)
        finally:
            w.stop()
        lines = sorted(v[1] for c in post.calls for s in c["streams"] for v in s["values"])
        assert lines == sorted(f"m{i}" for i in range(10))
