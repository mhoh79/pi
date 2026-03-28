"""Tests for network/shared/messages.py – Message dataclass."""

import time

from messages import Message


class TestMessageToDict:
    def test_round_trip(self):
        msg = Message(
            topic="sensor-1/temperature",
            source="sensor-1",
            timestamp=1700000000.0,
            payload={"value": 23.4, "unit": "C"},
            quality="good",
            sequence=42,
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)

        assert restored.topic == msg.topic
        assert restored.source == msg.source
        assert restored.timestamp == msg.timestamp
        assert restored.payload == msg.payload
        assert restored.quality == msg.quality
        assert restored.sequence == msg.sequence

    def test_to_dict_keys(self):
        msg = Message(
            topic="t", source="s", timestamp=0.0, payload={"x": 1}
        )
        d = msg.to_dict()
        assert set(d.keys()) == {
            "topic", "source", "timestamp", "payload", "quality", "sequence"
        }

    def test_from_dict_defaults(self):
        d = {"topic": "t", "source": "s", "timestamp": 1.0}
        msg = Message.from_dict(d)
        assert msg.payload == {}
        assert msg.quality == "good"
        assert msg.sequence == 0

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "topic": "t", "source": "s", "timestamp": 1.0,
            "payload": {}, "extra_field": "ignored"
        }
        msg = Message.from_dict(d)
        assert msg.topic == "t"
