"""Tests for network/shared/models.py – Pydantic models and conversions."""

from models import SensorReading, ControlOutput, AlarmEvent


# ── SensorReading ───────────────────────────────────────────────────────────


class TestSensorReading:
    def test_to_dict_legacy_shape(self):
        sr = SensorReading(
            topic="rpi-net/sensor/sensor-1/temp",
            source="sensor-1",
            timestamp=1700000000.0,
            value=23.4,
            unit="C",
            raw_key="temp",
            quality="good",
            sequence=1,
        )
        d = sr.to_dict()
        assert d["topic"] == "rpi-net/sensor/sensor-1/temp"
        assert d["source"] == "sensor-1"
        assert d["payload"]["value"] == 23.4
        assert d["payload"]["raw_key"] == "temp"
        assert d["payload"]["unit"] == "C"
        assert d["quality"] == "good"
        assert d["sequence"] == 1

    def test_from_legacy_dict(self):
        legacy = {
            "topic": "rpi-net/sensor/sensor-1/temp",
            "source": "sensor-1",
            "timestamp": 1700000000.0,
            "payload": {"value": 23.4, "raw_key": "temp", "unit": "C"},
            "quality": "good",
            "sequence": 5,
        }
        sr = SensorReading.from_legacy_dict(legacy)
        assert sr.value == 23.4
        assert sr.raw_key == "temp"
        assert sr.unit == "C"
        assert sr.sequence == 5

    def test_round_trip_to_dict_from_legacy(self):
        sr = SensorReading(
            topic="t", source="s", timestamp=1.0,
            value=42.0, unit="lux", raw_key="illuminance_lux",
            sequence=10,
        )
        d = sr.to_dict()
        restored = SensorReading.from_legacy_dict(d)
        assert restored.value == sr.value
        assert restored.raw_key == sr.raw_key
        assert restored.unit == sr.unit
        assert restored.topic == sr.topic

    def test_from_legacy_dict_minimal(self):
        """Handles dicts missing optional payload keys."""
        d = {"topic": "t", "source": "s",
             "timestamp": 1.0, "payload": {"value": 5.0}}
        sr = SensorReading.from_legacy_dict(d)
        assert sr.value == 5.0
        assert sr.raw_key == ""
        assert sr.unit == ""

    def test_from_legacy_dict_scalar_payload(self):
        """Handles non-dict payload (bare number)."""
        d = {"topic": "t", "source": "s", "timestamp": 1.0, "payload": 99.9}
        sr = SensorReading.from_legacy_dict(d)
        assert sr.value == 99.9


# ── ControlOutput ───────────────────────────────────────────────────────────


class TestControlOutput:
    def test_to_dict_legacy_shape(self):
        co = ControlOutput(
            topic="rpi-net/plc/plc-1/valve-1",
            source="plc",
            timestamp=1.0,
            output_id="valve_cooling",
            value=75.0,
        )
        d = co.to_dict()
        assert d["payload"]["value"] == 75.0
        assert d["payload"]["output_id"] == "valve_cooling"

    def test_from_legacy_dict(self):
        legacy = {
            "topic": "rpi-net/plc/plc-1/valve-1",
            "source": "plc",
            "timestamp": 1.0,
            "payload": {"value": 100.0, "output_id": "valve_cooling"},
            "quality": "good",
            "sequence": 3,
        }
        co = ControlOutput.from_legacy_dict(legacy)
        assert co.output_id == "valve_cooling"
        assert co.value == 100.0

    def test_round_trip(self):
        co = ControlOutput(
            topic="t", source="plc", timestamp=2.0,
            output_id="valve_cooling", value=50.0, sequence=7,
        )
        restored = ControlOutput.from_legacy_dict(co.to_dict())
        assert restored.output_id == co.output_id
        assert restored.value == co.value


# ── AlarmEvent ──────────────────────────────────────────────────────────────


class TestAlarmEvent:
    def test_to_dict_legacy_shape(self):
        ae = AlarmEvent(
            topic="rpi-net/plc/plc-1/alarm/high_temp",
            source="plc",
            timestamp=1.0,
            alarm_id="high_temp",
            message="Temperature too high",
            severity="WARNING",
            active=True,
        )
        d = ae.to_dict()
        assert d["payload"]["alarm_id"] == "high_temp"
        assert d["payload"]["active"] is True
        assert d["payload"]["severity"] == "WARNING"

    def test_from_legacy_dict(self):
        legacy = {
            "topic": "rpi-net/plc/plc-1/alarm/gas",
            "source": "plc",
            "timestamp": 1.0,
            "payload": {
                "alarm_id": "gas",
                "message": "Gas detected",
                "severity": "CRITICAL",
                "active": True,
            },
            "sequence": 2,
        }
        ae = AlarmEvent.from_legacy_dict(legacy)
        assert ae.alarm_id == "gas"
        assert ae.severity == "CRITICAL"
        assert ae.active is True

    def test_round_trip(self):
        ae = AlarmEvent(
            topic="t", source="plc", timestamp=3.0,
            alarm_id="proximity", message="Too close", active=False,
        )
        restored = AlarmEvent.from_legacy_dict(ae.to_dict())
        assert restored.alarm_id == ae.alarm_id
        assert restored.active == ae.active
        assert restored.message == ae.message


# ── Type detection (publish routing) ────────────────────────────────────────


class TestTypeDetection:
    """Verify the payload-key heuristic used by DdsTransport.publish()."""

    def test_sensor_reading_has_no_marker_keys(self):
        d = SensorReading(topic="t", source="s", value=1.0).to_dict()
        inner = d["payload"]
        assert "alarm_id" not in inner
        assert "output_id" not in inner

    def test_control_output_has_output_id(self):
        d = ControlOutput(topic="t", source="s", output_id="v").to_dict()
        assert "output_id" in d["payload"]

    def test_alarm_event_has_alarm_id(self):
        d = AlarmEvent(topic="t", source="s", alarm_id="x").to_dict()
        assert "alarm_id" in d["payload"]
