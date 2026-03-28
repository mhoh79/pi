"""Tests for network/plc/io_table.py – IOTable bidirectional mapping."""

import pytest

from io_table import IOTable, DEFAULT_INPUTS, DEFAULT_OUTPUTS


class TestDefaultMappings:
    def test_default_inputs_present(self):
        table = IOTable()
        assert set(table.list_inputs()) == set(DEFAULT_INPUTS.keys())

    def test_default_outputs_present(self):
        table = IOTable()
        assert set(table.list_outputs()) == set(DEFAULT_OUTPUTS.keys())


class TestInputLookup:
    def test_get_input_topic(self):
        table = IOTable()
        topic = table.get_input_topic("temp_room1")
        assert topic == DEFAULT_INPUTS["temp_room1"]

    def test_get_input_topic_unknown_raises(self):
        table = IOTable()
        with pytest.raises(KeyError):
            table.get_input_topic("nonexistent")

    def test_input_topic_to_name(self):
        table = IOTable()
        name = table.input_topic_to_name(DEFAULT_INPUTS["temp_room1"])
        assert name == "temp_room1"

    def test_input_topic_to_name_unknown(self):
        table = IOTable()
        assert table.input_topic_to_name("unknown/topic") is None


class TestOutputLookup:
    def test_get_output_topic(self):
        table = IOTable()
        topic = table.get_output_topic("valve_cooling")
        assert topic == DEFAULT_OUTPUTS["valve_cooling"]

    def test_get_output_topic_unknown_raises(self):
        table = IOTable()
        with pytest.raises(KeyError):
            table.get_output_topic("nonexistent")

    def test_output_topic_to_name(self):
        table = IOTable()
        name = table.output_topic_to_name(DEFAULT_OUTPUTS["alarm_gas"])
        assert name == "alarm_gas"

    def test_output_topic_to_name_unknown(self):
        table = IOTable()
        assert table.output_topic_to_name("unknown/topic") is None


class TestCustomMappings:
    def test_custom_inputs(self):
        table = IOTable(inputs={"my_input": "custom/topic"})
        assert table.get_input_topic("my_input") == "custom/topic"
        assert table.list_inputs() == ["my_input"]

    def test_custom_outputs(self):
        table = IOTable(outputs={"my_output": "custom/out"})
        assert table.get_output_topic("my_output") == "custom/out"
        assert table.list_outputs() == ["my_output"]


class TestAsDict:
    def test_as_dict_shape(self):
        table = IOTable()
        d = table.as_dict()
        assert "inputs" in d
        assert "outputs" in d
        assert d["inputs"] == DEFAULT_INPUTS
        assert d["outputs"] == DEFAULT_OUTPUTS

    def test_as_dict_is_copy(self):
        table = IOTable()
        d = table.as_dict()
        d["inputs"]["hacked"] = "value"
        # Original should be unaffected
        assert "hacked" not in table.as_dict()["inputs"]
