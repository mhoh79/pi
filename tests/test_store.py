"""Tests for network/gateway/store.py – TimeSeriesStore ring buffer."""

import time

from store import TimeSeriesStore


def _msg(topic: str, source: str, ts: float, value: float = 0.0) -> dict:
    """Create a minimal message dict."""
    return {
        "topic": topic,
        "source": source,
        "timestamp": ts,
        "payload": {"value": value},
    }


class TestAdd:
    def test_add_creates_topic(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0))
        assert "t1" in s.topics()

    def test_add_multiple_topics(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0))
        s.add("t2", _msg("t2", "s2", 2.0))
        assert set(s.topics()) == {"t1", "t2"}


class TestLatest:
    def test_latest_returns_most_recent(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0, value=10))
        s.add("t1", _msg("t1", "s1", 2.0, value=20))
        assert s.latest("t1")["payload"]["value"] == 20

    def test_latest_unknown_topic(self):
        s = TimeSeriesStore()
        assert s.latest("nonexistent") is None


class TestHistory:
    def test_returns_chronological_order(self):
        s = TimeSeriesStore()
        for i in range(5):
            s.add("t1", _msg("t1", "s1", float(i), value=i))
        h = s.history("t1", n=3)
        assert len(h) == 3
        assert h[0]["payload"]["value"] == 2
        assert h[-1]["payload"]["value"] == 4

    def test_returns_all_if_n_exceeds_count(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0))
        s.add("t1", _msg("t1", "s1", 2.0))
        h = s.history("t1", n=100)
        assert len(h) == 2

    def test_empty_topic(self):
        s = TimeSeriesStore()
        assert s.history("unknown") == []


class TestSince:
    def test_returns_only_newer(self):
        s = TimeSeriesStore()
        for i in range(5):
            s.add("t1", _msg("t1", "s1", float(i)))
        result = s.since("t1", 2.0)
        timestamps = [m["timestamp"] for m in result]
        assert all(t > 2.0 for t in timestamps)
        assert len(result) == 2  # ts=3.0, 4.0

    def test_since_unknown_topic(self):
        s = TimeSeriesStore()
        assert s.since("nonexistent", 0.0) == []


class TestAllLatest:
    def test_all_latest(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0, value=10))
        s.add("t2", _msg("t2", "s2", 2.0, value=20))
        s.add("t1", _msg("t1", "s1", 3.0, value=30))
        latest = s.all_latest()
        assert latest["t1"]["payload"]["value"] == 30
        assert latest["t2"]["payload"]["value"] == 20

    def test_all_latest_empty(self):
        s = TimeSeriesStore()
        assert s.all_latest() == {}


class TestRingBuffer:
    def test_maxlen_evicts_oldest(self):
        s = TimeSeriesStore(maxlen=3)
        for i in range(5):
            s.add("t1", _msg("t1", "s1", float(i), value=i))
        h = s.history("t1", n=100)
        assert len(h) == 3
        # Oldest surviving should be value=2
        assert h[0]["payload"]["value"] == 2


class TestNodes:
    def test_tracks_source_nodes(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "sensor-1", 100.0))
        s.add("t2", _msg("t2", "sensor-2", 200.0))
        nodes = s.nodes()
        assert nodes["sensor-1"] == 100.0
        assert nodes["sensor-2"] == 200.0

    def test_node_timestamp_updates(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "sensor-1", 100.0))
        s.add("t1", _msg("t1", "sensor-1", 200.0))
        assert s.nodes()["sensor-1"] == 200.0

    def test_nodes_returns_copy(self):
        s = TimeSeriesStore()
        s.add("t1", _msg("t1", "s1", 1.0))
        nodes = s.nodes()
        nodes["s1"] = 999.0
        assert s.nodes()["s1"] == 1.0


class TestTopics:
    def test_sorted(self):
        s = TimeSeriesStore()
        s.add("zebra", _msg("zebra", "s1", 1.0))
        s.add("alpha", _msg("alpha", "s1", 1.0))
        assert s.topics() == ["alpha", "zebra"]
