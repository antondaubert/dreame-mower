"""Tests for dreame/const.py utility functions."""

import pytest
from homeassistant.components.lawn_mower import LawnMowerActivity

from custom_components.dreame_mower.dreame.const import (
    CUTTING_HEIGHT_ABSOLUTE_MAX_CM,
    CUTTING_HEIGHT_DEFAULT_MAX_CM,
    DeviceStatus,
    STATUS_MAPPING,
    cutting_height_max_cm,
    map_status_to_activity,
    supports_cutting_height,
)


class TestMapStatusToActivity:
    """Test map_status_to_activity helper."""

    def test_mowing(self):
        assert map_status_to_activity(DeviceStatus.MOWING) == LawnMowerActivity.MOWING

    def test_standby_and_paused(self):
        assert map_status_to_activity(DeviceStatus.STANDBY) == LawnMowerActivity.PAUSED
        assert map_status_to_activity(DeviceStatus.PAUSED) == LawnMowerActivity.PAUSED
        assert map_status_to_activity(DeviceStatus.MAINTENANCE_PAUSED) == LawnMowerActivity.PAUSED

    def test_error(self):
        assert map_status_to_activity(DeviceStatus.PAUSED_DUE_TO_ERRORS) == LawnMowerActivity.ERROR

    def test_returning(self):
        assert map_status_to_activity(DeviceStatus.RETURNING_TO_CHARGE) == LawnMowerActivity.RETURNING

    def test_docked_states(self):
        for status in (DeviceStatus.CHARGING, DeviceStatus.MAPPING,
                       DeviceStatus.CHARGING_COMPLETE, DeviceStatus.UPDATING,
                       DeviceStatus.CHARGING_PAUSED_HIGH_TEMPERATURE,
                       DeviceStatus.CHARGING_PAUSED_LOW_TEMPERATURE):
            assert map_status_to_activity(status) == LawnMowerActivity.DOCKED

    def test_unknown_status_defaults_to_docked(self):
        assert map_status_to_activity(9999) == LawnMowerActivity.DOCKED


class TestStatusMapping:
    """Test STATUS_MAPPING labels for the device-status property (2:1)."""

    def test_charging_paused_temperature_codes(self):
        # Codes 15/16 are reported on the device-status property as well as on the
        # charging-status property, so they must resolve on both.
        assert STATUS_MAPPING[DeviceStatus.CHARGING_PAUSED_HIGH_TEMPERATURE] == "charging_paused_high_temperature"
        assert STATUS_MAPPING[DeviceStatus.CHARGING_PAUSED_LOW_TEMPERATURE] == "charging_paused_low_temperature"

    def test_maintenance_paused(self):
        assert STATUS_MAPPING[DeviceStatus.MAINTENANCE_PAUSED] == "maintenance_paused"


class TestCuttingHeightSupport:
    """Test the model-dependent cutting height helpers."""

    @pytest.mark.parametrize(
        "model",
        ["dreame.mower.g2408", "dreame.mower.p2255", "dreame.mower.g2541e", "mova.mower.g2529b"],
    )
    def test_adjustable_models_are_supported(self, model):
        assert supports_cutting_height(model) is True

    @pytest.mark.parametrize("model", ["mova.mower.g2405a", "mova.mower.g2405c"])
    def test_fixed_height_models_are_unsupported(self, model):
        assert supports_cutting_height(model) is False

    def test_default_models_top_out_at_seven_centimeters(self):
        assert cutting_height_max_cm("dreame.mower.g2408") == CUTTING_HEIGHT_DEFAULT_MAX_CM

    @pytest.mark.parametrize("model", ["dreame.mower.g2541e", "mova.mower.g2529b"])
    def test_extended_models_top_out_at_ten_centimeters(self, model):
        assert cutting_height_max_cm(model) == CUTTING_HEIGHT_ABSOLUTE_MAX_CM

    def test_unknown_models_fall_back_to_the_default_range(self):
        assert supports_cutting_height("dreame.mower.x9999") is True
        assert cutting_height_max_cm("dreame.mower.x9999") == CUTTING_HEIGHT_DEFAULT_MAX_CM

