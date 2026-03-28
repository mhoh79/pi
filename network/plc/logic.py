"""
logic.py - Control logic for the PLC scan cycle.

ControlLogic.execute() receives a dict of current input values (keyed by
logical name) and returns a dict of output values (also keyed by logical
name).  The PLC's main loop calls this once per scan cycle and writes the
returned values to the physical outputs via the transport layer.

Temperature control example
----------------------------
  temp_room1 > 28 °C  → valve_cooling = 100 %, alarm_high_temp = 1
  temp_room1 < 25 °C  → valve_cooling =   0 %, alarm_high_temp = 0
  25 ≤ temp ≤ 28      → proportional: valve_cooling = (temp - 25) / 3 * 100 %
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Threshold constants (easy to override in unit tests or subclasses)
TEMP_HIGH: float = 28.0   # °C  – full cooling / raise alarm
TEMP_LOW: float = 25.0   # °C  – cooling off  / clear alarm
TEMP_RANGE: float = TEMP_HIGH - TEMP_LOW  # 3.0 °C proportional band

GAS_HIGH: float = 200.0  # ppm – raise gas alarm
GAS_LOW: float = 150.0  # ppm – clear gas alarm

DISTANCE_MIN: float = 30.0   # cm  – raise proximity alarm
DISTANCE_CLR: float = 40.0   # cm  – clear proximity alarm


class ControlLogic:
    """Stateless (pure-function) control logic block.

    The class is deliberately kept stateless so that it is easy to test
    and replace.  If you need latching outputs or timers, add state as
    instance attributes and initialise them in __init__.
    """

    def __init__(self) -> None:
        # Retain last computed outputs so the REST status endpoint can
        # serve them without re-running the logic.
        self._last_outputs: dict[str, float | int | bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self, inputs: dict[str, float | int | bool | None]
    ) -> dict[str, float | int | bool]:
        """Run one scan cycle and return the desired output values.

        Parameters
        ----------
        inputs:
            Mapping of logical input name → current value.  Values may be
            None if the corresponding sensor has not yet published data.

        Returns
        -------
        dict
            Mapping of logical output name → desired value.
            ``valve_cooling`` is a percentage (0–100).
            ``alarm_high_temp`` is 1 (active) or 0 (clear).
        """
        outputs: dict[str, float | int | bool] = {}

        # ---- Temperature / cooling control ----------------------------
        temp = self._coerce_float(inputs.get("temp_room1"))

        if temp is None:
            # Sensor offline – fail-safe: leave cooling as-is, raise alarm
            logger.warning("temp_room1 is unavailable; retaining last outputs")
            outputs["valve_cooling"] = self._last_outputs.get(
                "valve_cooling", 0)
            outputs["alarm_high_temp"] = self._last_outputs.get(
                "alarm_high_temp", 1)
        elif temp > TEMP_HIGH:
            outputs["valve_cooling"] = 100
            outputs["alarm_high_temp"] = 1
            logger.debug(
                "temp=%.2f > %.1f → full cooling, alarm ON", temp, TEMP_HIGH)
        elif temp < TEMP_LOW:
            outputs["valve_cooling"] = 0
            outputs["alarm_high_temp"] = 0
            logger.debug(
                "temp=%.2f < %.1f → cooling OFF, alarm clear", temp, TEMP_LOW)
        else:
            # Proportional band
            ratio = (temp - TEMP_LOW) / TEMP_RANGE
            outputs["valve_cooling"] = round(ratio * 100, 1)
            outputs["alarm_high_temp"] = 0
            logger.debug(
                "temp=%.2f in band → valve_cooling=%.1f%%", temp, outputs["valve_cooling"]
            )

        # ---- Gas alarm (MQ-2) ----------------------------------------
        gas = self._coerce_float(inputs.get("gas_room1"))

        if gas is None:
            outputs["alarm_gas"] = self._last_outputs.get("alarm_gas", 0)
        elif gas > GAS_HIGH:
            outputs["alarm_gas"] = 1
            logger.debug("gas=%.1f ppm > %.1f → alarm ON", gas, GAS_HIGH)
        elif gas < GAS_LOW:
            outputs["alarm_gas"] = 0
            logger.debug("gas=%.1f ppm < %.1f → alarm clear", gas, GAS_LOW)
        else:
            outputs["alarm_gas"] = self._last_outputs.get("alarm_gas", 0)

        # ---- Proximity alarm (HC-SR04) ---------------------------------
        dist = self._coerce_float(inputs.get("distance_1"))

        if dist is None:
            outputs["alarm_proximity"] = self._last_outputs.get(
                "alarm_proximity", 0)
        elif dist < DISTANCE_MIN:
            outputs["alarm_proximity"] = 1
            logger.debug("dist=%.1f cm < %.1f → proximity alarm ON",
                         dist, DISTANCE_MIN)
        elif dist > DISTANCE_CLR:
            outputs["alarm_proximity"] = 0
            logger.debug(
                "dist=%.1f cm > %.1f → proximity alarm clear", dist, DISTANCE_CLR)
        else:
            outputs["alarm_proximity"] = self._last_outputs.get(
                "alarm_proximity", 0)

        self._last_outputs = dict(outputs)
        return outputs

    @property
    def last_outputs(self) -> dict[str, float | int | bool]:
        """Most recent output values (empty dict before first cycle)."""
        return dict(self._last_outputs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning("Cannot convert %r to float", value)
            return None
