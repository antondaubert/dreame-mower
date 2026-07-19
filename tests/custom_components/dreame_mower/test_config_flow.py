"""Tests for config_flow utility functions."""

import pytest
from unittest.mock import Mock, PropertyMock, patch
from custom_components.dreame_mower.config_flow import (
    _device_type_for_model,
    DEVICE_TYPE_MOWER,
    DEVICE_TYPE_SWBOT,
    DreameMowerOptionsFlow,
    NOTIFICATION_INFORMATION,
    NOTIFICATION_WARNING,
    NOTIFICATION_ERROR,
)
from custom_components.dreame_mower.const import CONF_NOTIFY, CONF_MAP_ROTATION


class TestDeviceTypeForModel:
    """Test _device_type_for_model helper."""

    def test_mower_model(self):
        assert _device_type_for_model("dreame.mower.p2255") == DEVICE_TYPE_MOWER

    def test_mova_model(self):
        assert _device_type_for_model("mova.mower.g2405a") == DEVICE_TYPE_MOWER

    def test_swbot_model(self):
        assert _device_type_for_model("dreame.swbot.g2509") == DEVICE_TYPE_SWBOT

    def test_unknown_model_defaults_to_mower(self):
        assert _device_type_for_model("some.unknown.model") == DEVICE_TYPE_MOWER


class TestOptionsFlow:
    """Test DreameMowerOptionsFlow."""

    @pytest.mark.asyncio
    async def test_filters_invalid_notification_types(self):
        """Test that invalid notification types like mqtt_discovery are filtered out."""
        # Create a mock config entry with old notification settings
        mock_config_entry = Mock()
        mock_config_entry.options = {
            CONF_NOTIFY: [NOTIFICATION_WARNING, NOTIFICATION_ERROR, "mqtt_discovery"],
            CONF_MAP_ROTATION: 0,
        }
        
        # Create options flow instance and patch config_entry property
        options_flow = DreameMowerOptionsFlow()
        with patch.object(
            type(options_flow), 'config_entry', new_callable=PropertyMock, return_value=mock_config_entry
        ):
            # Call async_step_init with no user input to get the form
            result = await options_flow.async_step_init(user_input=None)
        
        # Extract the default value for CONF_NOTIFY from the schema
        # In voluptuous, Required fields with defaults store the default in the key
        schema_dict = result["data_schema"].schema
        for key in schema_dict:
            if hasattr(key, 'schema') and key.schema == CONF_NOTIFY:
                default_notify = key.default()
                break
        
        # Verify mqtt_discovery was filtered out
        assert "mqtt_discovery" not in default_notify
        assert NOTIFICATION_WARNING in default_notify
        assert NOTIFICATION_ERROR in default_notify
        assert len(default_notify) == 2

    @pytest.mark.asyncio
    async def test_rotation_accepts_string_values(self):
        """The frontend submits radio values as strings; the schema must coerce them."""
        mock_config_entry = Mock()
        mock_config_entry.options = {CONF_MAP_ROTATION: 0}

        options_flow = DreameMowerOptionsFlow()
        with patch.object(
            type(options_flow), 'config_entry', new_callable=PropertyMock, return_value=mock_config_entry
        ):
            result = await options_flow.async_step_init(user_input=None)

        schema = result["data_schema"]
        for value in ("0", "90", "180", "270"):
            validated = schema({
                CONF_NOTIFY: [],
                CONF_MAP_ROTATION: value,
                "map_show_title": True,
                "map_show_legend": True,
                "map_padding": 50,
            })
            assert validated[CONF_MAP_ROTATION] == int(value)
