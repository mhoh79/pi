"""
messages.py – Message schema and helper constructors for the RPi simulation network.

All data flowing through the network is wrapped in a :class:`Message`.
Helper functions (``make_temperature``, ``make_humidity``, etc.) produce
correctly-typed messages without boilerplate.

Example
-------
    from messages import make_temperature

    msg  = make_temperature(source="sensor-1", value=23.4, unit="C")
    d    = msg.to_dict()           # serialise to plain dict (JSON-safe)
    msg2 = Message.from_dict(d)    # round-trip
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """
    Envelope for every datum that crosses the network.

    Attributes
    ----------
    topic:
        Hierarchical routing key, e.g. ``"sensor-1/temperature"``.
    source:
        Node ID that produced the message, e.g. ``"sensor-1"``.
    timestamp:
        Unix epoch seconds (float) when the reading was taken.
    payload:
        Arbitrary key/value data specific to the measurement type.
    quality:
        Data quality flag – ``"good"``, ``"uncertain"``, or ``"bad"``.
    sequence:
        Monotonically increasing counter per source; useful for detecting
        dropped messages.
    """

    topic: str
    source: str
    timestamp: float
    payload: Dict[str, Any]
    quality: str = "good"
    sequence: int = 0

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict that is safe to serialise as JSON."""
        return {
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "quality": self.quality,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """
        Reconstruct a :class:`Message` from a plain dict.

        Unknown keys are silently ignored so that future schema additions do
        not break older consumers.
        """
        return cls(
            topic=data["topic"],
            source=data["source"],
            timestamp=float(data["timestamp"]),
            payload=data.get("payload", {}),
            quality=data.get("quality", "good"),
            sequence=int(data.get("sequence", 0)),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Module-level sequence counter per source node (best-effort; not thread-safe).
_seq_counters: Dict[str, int] = {}


def _next_seq(source: str) -> int:
    _seq_counters[source] = _seq_counters.get(source, 0) + 1
    return _seq_counters[source]


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Helper constructors
# ---------------------------------------------------------------------------


def make_temperature(
    source: str,
    value: float,
    unit: str = "C",
    sensor_id: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create a temperature :class:`Message`."""
    return Message(
        topic=f"{source}/temperature",
        source=source,
        timestamp=_now(),
        payload={
            "value": round(value, 4),
            "unit": unit,
            "sensor_id": sensor_id or source,
        },
        quality=quality,
        sequence=_next_seq(source),
    )


def make_humidity(
    source: str,
    value: float,
    unit: str = "%RH",
    sensor_id: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create a relative-humidity :class:`Message`."""
    return Message(
        topic=f"{source}/humidity",
        source=source,
        timestamp=_now(),
        payload={
            "value": round(value, 4),
            "unit": unit,
            "sensor_id": sensor_id or source,
        },
        quality=quality,
        sequence=_next_seq(source),
    )


def make_pressure(
    source: str,
    value: float,
    unit: str = "hPa",
    sensor_id: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create a barometric-pressure :class:`Message`."""
    return Message(
        topic=f"{source}/pressure",
        source=source,
        timestamp=_now(),
        payload={
            "value": round(value, 4),
            "unit": unit,
            "sensor_id": sensor_id or source,
        },
        quality=quality,
        sequence=_next_seq(source),
    )


def make_light(
    source: str,
    value: float,
    unit: str = "lux",
    sensor_id: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create an illuminance :class:`Message`."""
    return Message(
        topic=f"{source}/light",
        source=source,
        timestamp=_now(),
        payload={
            "value": round(value, 4),
            "unit": unit,
            "sensor_id": sensor_id or source,
        },
        quality=quality,
        sequence=_next_seq(source),
    )


def make_acceleration(
    source: str,
    x: float,
    y: float,
    z: float,
    unit: str = "g",
    sensor_id: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create a 3-axis acceleration :class:`Message`."""
    return Message(
        topic=f"{source}/acceleration",
        source=source,
        timestamp=_now(),
        payload={
            "x": round(x, 6),
            "y": round(y, 6),
            "z": round(z, 6),
            "unit": unit,
            "sensor_id": sensor_id or source,
        },
        quality=quality,
        sequence=_next_seq(source),
    )


def make_control_output(
    source: str,
    output_id: str,
    value: Any,
    unit: Optional[str] = None,
    quality: str = "good",
) -> Message:
    """Create a PLC / controller output :class:`Message`."""
    payload: Dict[str, Any] = {
        "output_id": output_id,
        "value": value,
    }
    if unit is not None:
        payload["unit"] = unit
    return Message(
        topic=f"{source}/control/{output_id}",
        source=source,
        timestamp=_now(),
        payload=payload,
        quality=quality,
        sequence=_next_seq(source),
    )


def make_alarm(
    source: str,
    alarm_id: str,
    message: str,
    severity: str = "WARNING",
    active: bool = True,
    quality: str = "good",
) -> Message:
    """
    Create an alarm :class:`Message`.

    Parameters
    ----------
    severity:
        One of ``"INFO"``, ``"WARNING"``, ``"CRITICAL"``.
    active:
        ``True`` when the alarm condition is present; ``False`` when cleared.
    """
    return Message(
        topic=f"{source}/alarm/{alarm_id}",
        source=source,
        timestamp=_now(),
        payload={
            "alarm_id": alarm_id,
            "message": message,
            "severity": severity.upper(),
            "active": active,
        },
        quality=quality,
        sequence=_next_seq(source),
    )
