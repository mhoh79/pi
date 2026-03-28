"""Tests for network/plc/logic.py – PLC control logic."""

from logic import ControlLogic, TEMP_HIGH, TEMP_LOW, GAS_HIGH, GAS_LOW, DISTANCE_MIN, DISTANCE_CLR


class TestTemperatureControl:
    def test_above_high_threshold(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": 30.0})
        assert out["valve_cooling"] == 100
        assert out["alarm_high_temp"] == 1

    def test_below_low_threshold(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": 20.0})
        assert out["valve_cooling"] == 0
        assert out["alarm_high_temp"] == 0

    def test_at_midpoint_proportional(self):
        logic = ControlLogic()
        mid = (TEMP_HIGH + TEMP_LOW) / 2  # 26.5
        out = logic.execute({"temp_room1": mid})
        assert 0 < out["valve_cooling"] < 100
        assert out["alarm_high_temp"] == 0

    def test_at_low_threshold_exact(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": TEMP_LOW})
        # Exactly at TEMP_LOW → proportional band, ratio = 0 → 0%
        assert out["valve_cooling"] == 0

    def test_at_high_threshold_exact(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": TEMP_HIGH})
        # Exactly at TEMP_HIGH → still in band, ratio = 1.0 → 100%
        assert out["valve_cooling"] == 100.0

    def test_proportional_linearity(self):
        logic = ControlLogic()
        out_low = logic.execute({"temp_room1": TEMP_LOW + 1.0})
        out_high = logic.execute({"temp_room1": TEMP_LOW + 2.0})
        # Valve should increase linearly
        assert out_high["valve_cooling"] > out_low["valve_cooling"]


class TestGasAlarm:
    def test_above_high_threshold(self):
        logic = ControlLogic()
        out = logic.execute({"gas_room1": 250.0})
        assert out["alarm_gas"] == 1

    def test_below_low_threshold(self):
        logic = ControlLogic()
        out = logic.execute({"gas_room1": 100.0})
        assert out["alarm_gas"] == 0

    def test_in_deadband_retains_last(self):
        logic = ControlLogic()
        # First: alarm active
        logic.execute({"gas_room1": 250.0})
        # Then: value in dead band → retains last alarm state
        out = logic.execute({"gas_room1": 175.0})
        assert out["alarm_gas"] == 1

    def test_in_deadband_retains_clear(self):
        logic = ControlLogic()
        # First: alarm clear
        logic.execute({"gas_room1": 100.0})
        # Then: value in dead band → retains cleared state
        out = logic.execute({"gas_room1": 175.0})
        assert out["alarm_gas"] == 0


class TestProximityAlarm:
    def test_too_close(self):
        logic = ControlLogic()
        out = logic.execute({"distance_1": 10.0})
        assert out["alarm_proximity"] == 1

    def test_far_enough(self):
        logic = ControlLogic()
        out = logic.execute({"distance_1": 50.0})
        assert out["alarm_proximity"] == 0

    def test_in_deadband_retains_last(self):
        logic = ControlLogic()
        # Alarm active first
        logic.execute({"distance_1": 10.0})
        # Then in dead band
        out = logic.execute({"distance_1": 35.0})
        assert out["alarm_proximity"] == 1


class TestFailSafe:
    def test_none_temp_retains_last_outputs(self):
        logic = ControlLogic()
        # Set a known state first
        logic.execute({"temp_room1": 30.0})
        # Now sensor goes offline
        out = logic.execute({"temp_room1": None})
        assert out["valve_cooling"] == 100
        assert out["alarm_high_temp"] == 1

    def test_none_on_first_cycle(self):
        logic = ControlLogic()
        out = logic.execute({})
        # Default fail-safe for temp: 0 cooling, alarm ON
        assert out["valve_cooling"] == 0
        assert out["alarm_high_temp"] == 1

    def test_none_gas_retains_default(self):
        logic = ControlLogic()
        out = logic.execute({})
        # Default for gas: alarm OFF
        assert out["alarm_gas"] == 0


class TestLastOutputs:
    def test_initial_empty(self):
        logic = ControlLogic()
        assert logic.last_outputs == {}

    def test_after_execute(self):
        logic = ControlLogic()
        logic.execute(
            {"temp_room1": 20.0, "gas_room1": 100.0, "distance_1": 50.0})
        last = logic.last_outputs
        assert "valve_cooling" in last
        assert "alarm_gas" in last
        assert "alarm_proximity" in last

    def test_last_outputs_is_copy(self):
        logic = ControlLogic()
        logic.execute({"temp_room1": 20.0})
        last = logic.last_outputs
        last["valve_cooling"] = 999
        # Internal state should not be affected
        assert logic.last_outputs["valve_cooling"] != 999


class TestCoerceFloat:
    def test_string_number(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": "27.0"})
        assert "valve_cooling" in out

    def test_non_numeric_string(self):
        logic = ControlLogic()
        out = logic.execute({"temp_room1": "not_a_number"})
        # Should be treated as None (unavailable)
        assert out["alarm_high_temp"] == 1  # fail-safe alarm ON
