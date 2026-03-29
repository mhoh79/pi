"""
dds_types.py – CycloneDDS IDL type definitions for the RPi simulation network.

These ``@dataclass`` / ``IdlStruct`` classes are the wire format used by
CycloneDDS.  They intentionally mirror the Pydantic models in
``models.py`` but use only IDL-compatible primitive types.

All fields carry defaults so that CycloneDDS can deserialise partial
samples without raising.

NOTE: Do NOT add ``from __future__ import annotations`` here.
CycloneDDS IDL requires concrete type objects in annotations, not
PEP 563 lazy string references.
"""

from dataclasses import dataclass

from cyclonedds.idl import IdlStruct

# ---------------------------------------------------------------------------
# DDS Topic name constants
# ---------------------------------------------------------------------------

TOPIC_SENSOR_DATA: str = "SensorData"
TOPIC_CONTROL_DATA: str = "ControlData"
TOPIC_ALARM_DATA: str = "AlarmData"


# ---------------------------------------------------------------------------
# IDL structs
# ---------------------------------------------------------------------------


@dataclass
class DdsSensorReading(IdlStruct, keylist=["topic"]):
    """Wire type for sensor measurements (maps to the *SensorData* topic)."""

    topic: str = ""
    source: str = ""
    timestamp: float = 0.0
    value: float = 0.0
    unit: str = ""
    raw_key: str = ""
    quality: str = "good"
    sequence: int = 0


@dataclass
class DdsControlOutput(IdlStruct, keylist=["topic"]):
    """Wire type for PLC outputs (maps to the *ControlData* topic)."""

    topic: str = ""
    source: str = ""
    timestamp: float = 0.0
    output_id: str = ""
    value: float = 0.0
    unit: str = ""
    quality: str = "good"
    sequence: int = 0


@dataclass
class DdsAlarmEvent(IdlStruct, keylist=["topic"]):
    """Wire type for PLC alarm events (maps to the *AlarmData* topic)."""

    topic: str = ""
    source: str = ""
    timestamp: float = 0.0
    alarm_id: str = ""
    message: str = ""
    severity: str = "WARNING"
    active: bool = True
    sequence: int = 0
