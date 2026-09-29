"""Tests for the Dreame Mower firmware update entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.update import UpdateDeviceClass, UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError

from custom_components.dreame_mower.const import DATA_COORDINATOR, DOMAIN
from custom_components.dreame_mower.dreame.device import DreameCommandError
from custom_components.dreame_mower.update import DreameMowerFirmwareUpdate, async_setup_entry


def _make_coordinator(**overrides):
    coordinator = MagicMock()
    coordinator.device_mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device_name = "Test Mower"
    coordinator.device_model = "dreame.mower.g2408"
    coordinator.device_serial = "SN123"
    coordinator.device_manufacturer = "Dreametech™"
    coordinator.device_firmware = "4.3.6_0625"
    coordinator.device_connected = True
    coordinator.device_online = True
    coordinator.device_firmware_status_checked = True
    coordinator.device_latest_firmware = "4.3.6_0668"
    coordinator.device_firmware_release_notes = "1. Improved positioning."
    coordinator.device_firmware_update_in_progress = False
    coordinator.device_firmware_update_percentage = None
    coordinator.async_start_firmware_update = AsyncMock(return_value=True)
    for name, value in overrides.items():
        setattr(coordinator, name, value)
    return coordinator


def _make_entity(**overrides):
    entity = DreameMowerFirmwareUpdate(_make_coordinator(**overrides))
    entity.hass = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_setup_adds_the_firmware_update_entity():
    """The platform adds one firmware update entity for the mower."""
    coordinator = _make_coordinator()
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry_id": {DATA_COORDINATOR: coordinator}}}
    entry = MagicMock()
    entry.entry_id = "entry_id"
    added_entities: list = []

    await async_setup_entry(hass, entry, added_entities.extend)

    assert len(added_entities) == 1
    entity = added_entities[0]
    assert isinstance(entity, DreameMowerFirmwareUpdate)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_firmware"
    assert entity.device_class == UpdateDeviceClass.FIRMWARE
    assert entity.supported_features == (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
    )


def test_an_available_update_offers_the_newer_version():
    """The cloud's newer release is the latest version."""
    entity = _make_entity()

    assert entity.installed_version == "4.3.6_0625"
    assert entity.latest_version == "4.3.6_0668"


def test_an_up_to_date_mower_reports_its_own_version_as_latest():
    """With nothing newer, the installed version is the latest one."""
    entity = _make_entity(device_latest_firmware=None)

    assert entity.latest_version == "4.3.6_0625"


def test_the_latest_version_is_unknown_until_the_cloud_was_asked():
    """Before the first version check nothing is known about newer releases."""
    entity = _make_entity(device_firmware_status_checked=False, device_latest_firmware=None)

    assert entity.latest_version is None


def test_an_unknown_installed_version_is_not_reported():
    """The placeholder for a version not reported yet is not a version."""
    entity = _make_entity(device_firmware="Unknown")

    assert entity.installed_version is None


def test_a_running_update_reports_its_progress():
    """Progress comes from the mower while it updates."""
    entity = _make_entity(
        device_firmware_update_in_progress=True,
        device_firmware_update_percentage=42,
    )

    assert entity.in_progress is True
    assert entity.update_percentage == 42


@pytest.mark.asyncio
async def test_release_notes_are_those_of_the_available_update():
    """The release notes are the ones the cloud gave for the newer release."""
    entity = _make_entity()

    assert await entity.async_release_notes() == "1. Improved positioning."


@pytest.mark.asyncio
async def test_install_starts_the_update():
    """Installing asks the mower to fetch the available firmware."""
    entity = _make_entity()

    await entity.async_install(None, False)

    entity.coordinator.async_start_firmware_update.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [
        ValueError("The mower needs at least 20% battery to update its firmware"),
        DreameCommandError("The firmware update was refused: device busy"),
    ],
)
@pytest.mark.asyncio
async def test_install_passes_on_why_the_update_did_not_start(error):
    """A refused or impossible update reaches the user with its reason."""
    entity = _make_entity(async_start_firmware_update=AsyncMock(side_effect=error))

    with pytest.raises(HomeAssistantError, match=str(error)):
        await entity.async_install(None, False)
