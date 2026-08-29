import json

from stats import Stats, StatsFlusher


def label(device, mtype, fmt):
    return {"source": "mqtt", "device": device, "type": mtype, "format": fmt}


class TestStats:
    def test_counts_accumulate_by_bucket(self):
        s = Stats()
        s.record(label("kitchen", "state", "json"))
        s.record(label("kitchen", "state", "json"))
        s.record(label("porch", "availability", "text"))

        snap = s.snapshot()
        assert snap["total"] == 3
        assert snap["byDevice"] == {"kitchen": 2, "porch": 1}
        assert snap["byType"] == {"state": 2, "availability": 1}
        assert snap["byFormat"] == {"json": 2, "text": 1}

    def test_snapshot_shape_matches_old_flow(self):
        assert set(Stats().snapshot()) == {"total", "byDevice", "byType", "byFormat"}

    def test_snapshot_is_a_copy(self):
        s = Stats()
        s.record(label("d", "t", "json"))
        snap = s.snapshot()
        snap["byDevice"]["d"] = 999
        assert s.snapshot()["byDevice"]["d"] == 1

    def test_missing_labels_fall_back_to_unknown(self):
        s = Stats()
        s.record({"source": "mqtt"})
        snap = s.snapshot()
        assert snap["byDevice"] == {"unknown": 1}


class _CollectingWriter:
    def __init__(self):
        self.entries = []

    def enqueue(self, labels, ts_ns, line):
        self.entries.append((labels, ts_ns, line))


class TestStatsFlusher:
    def test_flush_once_enqueues_a_stats_stream(self):
        s = Stats()
        s.record(label("d", "t", "json"))
        w = _CollectingWriter()
        StatsFlusher(s, w, clock=lambda: 42).flush_once()

        assert len(w.entries) == 1
        labels, ts, line = w.entries[0]
        assert labels == {"source": "mqtt-logger", "type": "stats"}
        assert ts == 42
        assert json.loads(line)["total"] == 1
