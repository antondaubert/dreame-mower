"""Tests for DreameMowerEntity base class."""

from unittest.mock import MagicMock

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.dreame_mower.entity import DreameMowerEntity
from custom_components.dreame_mower.const import DOMAIN


def _make_coordinator(
    mac="AA:BB:CC:DD:EE:FF",
    name="Test Mower",
    model="dreame.mower.test",
    serial="SN123",
    manufacturer="Dreametech™",
    firmware="1.0.0",
    connected=True,
    online=True,
):
    coordinator = MagicMock()
    coordinator.device_mac = mac
    coordinator.device_name = name
    coordinator.device_model = model
    coordinator.device_serial = serial
    coordinator.device_manufacturer = manufacturer
    coordinator.device_firmware = firmware
    coordinator.device_connected = connected
    coordinator.device_online = online
    return coordinator


def _make_entity(coordinator=None, key="test_key"):
    """Instantiate DreameMowerEntity using __new__ to bypass CoordinatorEntity setup."""
    entity = DreameMowerEntity.__new__(DreameMowerEntity)
    entity.coordinator = coordinator or _make_coordinator()
    entity._entity_description_key = key
    entity._attr_has_entity_name = True
    return entity


def test_unique_id_format():
    entity = _make_entity(_make_coordinator(mac="AA:BB:CC:DD:EE:FF"), key="sensor_battery")
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_sensor_battery"


def test_unique_id_falls_back_to_unknown_when_no_mac():
    entity = _make_entity(_make_coordinator(mac=None), key="sensor_battery")
    assert entity.unique_id == "unknown_sensor_battery"


def test_available_true_when_connected():
    entity = _make_entity(_make_coordinator(connected=True))
    assert entity.available is True


def test_available_false_when_disconnected():
    entity = _make_entity(_make_coordinator(connected=False))
    assert entity.available is False


def test_available_false_when_offline():
    # The transport link may be up while the robot itself is offline.
    entity = _make_entity(_make_coordinator(connected=True, online=False))
    assert entity.available is False


def test_device_info_required_fields():
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)
    info = entity.device_info

    assert (CONNECTION_NETWORK_MAC, "AA:BB:CC:DD:EE:FF") in info["connections"]
    assert (DOMAIN, "AA:BB:CC:DD:EE:FF") in info["identifiers"]
    assert info["name"] == "Test Mower"
    assert info["manufacturer"] == "Dreametech™"
    assert info["model"] == "dreame.mower.test"
    assert info["serial_number"] == "SN123"
    assert info["suggested_area"] == "Garden"


def test_device_info_includes_sw_version_when_firmware_present():
    entity = _make_entity(_make_coordinator(firmware="2.5.0"))
    assert entity.device_info["sw_version"] == "2.5.0"


def test_device_info_excludes_sw_version_when_firmware_none():
    entity = _make_entity(_make_coordinator(firmware=None))
    assert "sw_version" not in entity.device_info


def test_has_entity_name_is_true():
    entity = _make_entity()
    assert entity._attr_has_entity_name is True
