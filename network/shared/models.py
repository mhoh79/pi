"""
models.py – Pydantic data models for the RPi simulation network.

These are the canonical schema definitions.  Every other representation
(dict, DDS IdlStruct, JSON) converts to/from these models.

Three model types mirror the three DDS topics:
  - SensorReading  → SensorData
  - ControlOutput  → ControlData
  - AlarmEvent     → AlarmData
"""

from __future__ import annotations

import time
from typing import Any, Dict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SensorReading
# ---------------------------------------------------------------------------


class SensorReading(BaseModel):
    """A single scalar sensor measurement."""

    topic: str = ""
    source: str = ""
    timestamp: float = Field(default_factory=time.time)
    value: float = 0.0
    unit: str = ""
    raw_key: str = ""
    quality: str = "good"
    sequence: int = 0

    # -- conversions ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict matching the legacy ``Message.to_dict()`` shape."""
        return {
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": {"value": self.value, "raw_key": self.raw_key, "unit": self.unit},
            "quality": self.quality,
            "sequence": self.sequence,
        }

    def to_dds(self) -> Any:
        """Convert to a CycloneDDS ``DdsSensorReading`` IdlStruct."""
        from dds_types import DdsSensorReading

        return DdsSensorReading(
            topic=self.topic,
            source=self.source,
            timestamp=self.timestamp,
            value=self.value,
            unit=self.unit,
            raw_key=self.raw_key,
            quality=self.quality,
            sequence=self.sequence,
        )

    @classmethod
    def from_dds(cls, dds_obj: Any) -> SensorReading:
        """Construct from a ``DdsSensorReading`` IdlStruct."""
        return cls(
            topic=dds_obj.topic,
            source=dds_obj.source,
            timestamp=dds_obj.timestamp,
            value=dds_obj.value,
            unit=dds_obj.unit,
            raw_key=dds_obj.raw_key,
            quality=dds_obj.quality,
            sequence=dds_obj.sequence,
        )

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> SensorReading:
        """Parse from the existing ``Message.to_dict()`` format."""
        payload = d.get("payload", {})
        if isinstance(payload, dict):
            value = float(payload.get("value", 0.0))
            raw_key = str(payload.get("raw_key", ""))
            unit = str(payload.get("unit", ""))
        else:
            value = float(payload)
            raw_key = ""
            unit = ""
        return cls(
            topic=d.get("topic", ""),
            source=d.get("source", ""),
            timestamp=float(d.get("timestamp", 0.0)),
            value=value,
            unit=unit,
            raw_key=raw_key,
            quality=d.get("quality", "good"),
            sequence=int(d.get("sequence", 0)),
        )


# ---------------------------------------------------------------------------
# ControlOutput
# ---------------------------------------------------------------------------


class ControlOutput(BaseModel):
    """A PLC output value (valve position, binary command, etc.)."""

    topic: str = ""
    source: str = ""
    timestamp: float = Field(default_factory=time.time)
    output_id: str = ""
    value: float = 0.0
    unit: str = ""
    quality: str = "good"
    sequence: int = 0

    # -- conversions ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict matching the legacy ``Message.to_dict()`` shape."""
        return {
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": {"value": self.value, "output_id": self.output_id, "unit": self.unit},
            "quality": self.quality,
            "sequence": self.sequence,
        }

    def to_dds(self) -> Any:
        """Convert to a CycloneDDS ``DdsControlOutput`` IdlStruct."""
        from dds_types import DdsControlOutput

        return DdsControlOutput(
            topic=self.topic,
            source=self.source,
            timestamp=self.timestamp,
            output_id=self.output_id,
            value=self.value,
            unit=self.unit,
            quality=self.quality,
            sequence=self.sequence,
        )

    @classmethod
    def from_dds(cls, dds_obj: Any) -> ControlOutput:
        """Construct from a ``DdsControlOutput`` IdlStruct."""
        return cls(
            topic=dds_obj.topic,
            source=dds_obj.source,
            timestamp=dds_obj.timestamp,
            output_id=dds_obj.output_id,
            value=dds_obj.value,
            unit=dds_obj.unit,
            quality=dds_obj.quality,
            sequence=dds_obj.sequence,
        )

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> ControlOutput:
        """Parse from the existing ``Message.to_dict()`` format."""
        payload = d.get("payload", {})
        if isinstance(payload, dict):
            value = float(payload.get("value", 0.0))
            output_id = str(payload.get("output_id", ""))
            unit = str(payload.get("unit", ""))
        else:
            value = float(payload)
            output_id = ""
            unit = ""
        return cls(
            topic=d.get("topic", ""),
            source=d.get("source", ""),
            timestamp=float(d.get("timestamp", 0.0)),
            value=value,
            output_id=output_id,
            unit=unit,
            quality=d.get("quality", "good"),
            sequence=int(d.get("sequence", 0)),
        )


# ---------------------------------------------------------------------------
# AlarmEvent
# ---------------------------------------------------------------------------


class AlarmEvent(BaseModel):
    """A PLC alarm event (raised or cleared)."""

    topic: str = ""
    source: str = ""
    timestamp: float = Field(default_factory=time.time)
    alarm_id: str = ""
    message: str = ""
    severity: str = "WARNING"
    active: bool = True
    sequence: int = 0

    # -- conversions ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict matching the legacy ``Message.to_dict()`` shape."""
        return {
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": {
                "alarm_id": self.alarm_id,
                "message": self.message,
                "severity": self.severity,
                "active": self.active,
            },
            "quality": "good",
            "sequence": self.sequence,
        }

    def to_dds(self) -> Any:
        """Convert to a CycloneDDS ``DdsAlarmEvent`` IdlStruct."""
        from dds_types import DdsAlarmEvent

        return DdsAlarmEvent(
            topic=self.topic,
            source=self.source,
            timestamp=self.timestamp,
            alarm_id=self.alarm_id,
            message=self.message,
            severity=self.severity,
            active=self.active,
            sequence=self.sequence,
        )

    @classmethod
    def from_dds(cls, dds_obj: Any) -> AlarmEvent:
        """Construct from a ``DdsAlarmEvent`` IdlStruct."""
        return cls(
            topic=dds_obj.topic,
            source=dds_obj.source,
            timestamp=dds_obj.timestamp,
            alarm_id=dds_obj.alarm_id,
            message=dds_obj.message,
            severity=dds_obj.severity,
            active=dds_obj.active,
            sequence=dds_obj.sequence,
        )

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> AlarmEvent:
        """Parse from the existing ``Message.to_dict()`` format."""
        payload = d.get("payload", {})
        if isinstance(payload, dict):
            alarm_id = str(payload.get("alarm_id", ""))
            message = str(payload.get("message", ""))
            severity = str(payload.get("severity", "WARNING"))
            active = bool(payload.get("active", True))
        else:
            alarm_id = ""
            message = str(payload)
            severity = "WARNING"
            active = True
        return cls(
            topic=d.get("topic", ""),
            source=d.get("source", ""),
            timestamp=float(d.get("timestamp", 0.0)),
            alarm_id=alarm_id,
            message=message,
            severity=severity,
            active=active,
            sequence=int(d.get("sequence", 0)),
        )
