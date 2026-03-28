"""
io_table.py - I/O mapping for the PLC.

Maps logical input/output names to their corresponding MQTT-style topics
used by the gateway. Update DEFAULT_INPUTS and DEFAULT_OUTPUTS to match
your physical installation.
"""

from __future__ import annotations

DEFAULT_INPUTS: dict[str, str] = {
    "temp_room1":  "rpi-net/sensor/sensor-1/temperature",
    "light_room1": "rpi-net/sensor/sensor-2/light",
}

DEFAULT_OUTPUTS: dict[str, str] = {
    "valve_cooling":   "rpi-net/plc/plc-1/valve-1",
    "alarm_high_temp": "rpi-net/plc/plc-1/alarm/high_temp",
}


class IOTable:
    """Bidirectional mapping between logical names and gateway topics."""

    def __init__(
        self,
        inputs: dict[str, str] | None = None,
        outputs: dict[str, str] | None = None,
    ) -> None:
        self._inputs: dict[str, str] = dict(inputs or DEFAULT_INPUTS)
        self._outputs: dict[str, str] = dict(outputs or DEFAULT_OUTPUTS)

    # ------------------------------------------------------------------
    # Input side (sensor topics → logical names)
    # ------------------------------------------------------------------

    def get_input_topic(self, name: str) -> str:
        """Return the gateway topic for the given logical input name.

        Raises KeyError if the name is not mapped.
        """
        return self._inputs[name]

    def list_inputs(self) -> list[str]:
        """Return all configured logical input names."""
        return list(self._inputs.keys())

    def input_topic_to_name(self, topic: str) -> str | None:
        """Reverse lookup: topic → logical name, or None if not found."""
        for name, t in self._inputs.items():
            if t == topic:
                return name
        return None

    # ------------------------------------------------------------------
    # Output side (logical names → actuator topics)
    # ------------------------------------------------------------------

    def get_output_topic(self, name: str) -> str:
        """Return the gateway topic for the given logical output name.

        Raises KeyError if the name is not mapped.
        """
        return self._outputs[name]

    def list_outputs(self) -> list[str]:
        """Return all configured logical output names."""
        return list(self._outputs.keys())

    def output_topic_to_name(self, topic: str) -> str | None:
        """Reverse lookup: topic → logical name, or None if not found."""
        for name, t in self._outputs.items():
            if t == topic:
                return name
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "inputs": dict(self._inputs),
            "outputs": dict(self._outputs),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"IOTable(inputs={list(self._inputs)}, "
            f"outputs={list(self._outputs)})"
        )
