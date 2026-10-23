"""Tests for Dreame Mower integration setup."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_mower import async_remove_entry, async_setup_entry
from custom_components.dreame_mower.config_flow import (
    CONF_ACCOUNT_TYPE,
    CONF_COUNTRY,
    CONF_DID,
    CONF_MAC,
    CONF_MODEL,
    CONF_SERIAL,
    DEVICE_TYPE_SWBOT,
)
from custom_components.dreame_mower.const import (
    DATA_COORDINATOR,
    DOMAIN,
    RAIN_POLL_INTERVAL_SECONDS,
    SCHEDULE_POLL_INTERVAL_SECONDS,
)


@pytest.fixture(autouse=True)
def setup_frontend():
    """Setup serves the map card; these tests run without the http component."""
    with patch("custom_components.dreame_mower.async_setup_frontend", AsyncMock()) as setup_frontend:
        yield setup_frontend


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Mower",
        data={
            CONF_NAME: "Test Mower",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_MODEL: "dreame.mower.test789",
            CONF_SERIAL: "MIN123456",
            CONF_DID: "test_device_456",
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_password",
            CONF_ACCOUNT_TYPE: "dreame",
            CONF_COUNTRY: "eu",
        },
        entry_id="test_init_entry",
    )


def _make_coordinator() -> MagicMock:
    """Build a mower coordinator stub whose awaited calls are real coroutines.

    Every method setup awaits has to be an AsyncMock: a bare MagicMock would
    raise TypeError, which setup swallows, so the assertions below would pass
    without the call ever having happened.
    """
    coordinator = MagicMock()
    coordinator.device_type = "mower"
    coordinator.supports_cutting_height = True
    coordinator.device = MagicMock()
    coordinator.device.fetch_vector_map = MagicMock(return_value=True)
    coordinator.device.load_stored_vector_map = MagicMock(return_value=True)
    coordinator.async_connect_device = AsyncMock(return_value=True)
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
    coordinator.async_request_refresh = AsyncMock(return_value=None)
    coordinator.async_fetch_consumable_data = AsyncMock(return_value=None)
    coordinator.async_fetch_mowing_preferences = AsyncMock(return_value=True)
    coordinator.async_fetch_device_settings = AsyncMock(return_value=None)
    coordinator.async_fetch_schedules = AsyncMock(return_value=True)
    coordinator.supports_rain_protection = True
    coordinator.supports_schedules = True
    coordinator.async_fetch_firmware_status = AsyncMock(return_value=None)
    coordinator.async_update_online_status = AsyncMock(return_value=None)
    coordinator.async_disconnect_device = AsyncMock(return_value=None)
    coordinator.async_refresh_map_extras = AsyncMock(return_value=None)
    coordinator.async_fetch_rain_protection_end = AsyncMock(return_value=True)
    coordinator.device.async_check_reachable = AsyncMock(return_value=True)
    return coordinator


async def test_async_setup_entry_fetches_vector_map_for_mowers(hass, setup_frontend):
    """Mower setup should preload vector map data before entity setup."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = _make_coordinator()

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=None),
    ) as forward_entry_setups:
        assert await async_setup_entry(hass, entry) is True
        await hass.async_block_till_done()

    coordinator.async_connect_device.assert_awaited_once()
    # The stored copy during setup, the mower's own maps right after.
    coordinator.device.load_stored_vector_map.assert_called_once_with()
    coordinator.device.fetch_vector_map.assert_called_once_with()
    coordinator.async_refresh_map_extras.assert_awaited_once_with()
    setup_frontend.assert_awaited_once_with(hass)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.async_fetch_mowing_preferences.assert_awaited_once()
    coordinator.async_fetch_device_settings.assert_awaited_once()
    coordinator.async_fetch_schedules.assert_awaited_once()
    forward_entry_setups.assert_awaited_once()
    assert hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR] is coordinator


async def test_stopping_home_assistant_drops_the_cloud_connection(hass):
    """The MQTT client must not outlive the event loop it hands pushes to."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = _make_coordinator()

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=None),
    ):
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_disconnect_device.assert_not_awaited()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    coordinator.async_disconnect_device.assert_awaited_once()


async def test_removing_the_entry_deletes_its_point_clouds(hass, tmp_path):
    """The clouds kept on disk go with the entry, those of other entries stay."""
    hass.config.config_dir = str(tmp_path)
    entry = _make_entry()
    ours = tmp_path / DOMAIN / "point_cloud" / entry.entry_id
    other = tmp_path / DOMAIN / "point_cloud" / "other"
    for directory in (ours, other):
        directory.mkdir(parents=True)
        (directory / "0.pcd").write_bytes(b"cloud")

    await async_remove_entry(hass, entry)

    assert not ours.exists()
    assert (other / "0.pcd").exists()
    # An entry that never kept a cloud is removed all the same.
    await async_remove_entry(hass, entry)


async def test_removing_the_entry_deletes_its_kept_work_log(hass, hass_storage):
    """The work log kept for the entry goes with it, that of another entry stays."""
    entry = _make_entry()
    ours, other = f"{DOMAIN}.work_log.{entry.entry_id}", f"{DOMAIN}.work_log.other"
    for key in (ours, other):
        hass_storage[key] = {"version": 1, "key": key, "data": {"entries": []}}

    await async_remove_entry(hass, entry)

    assert ours not in hass_storage
    assert other in hass_storage


async def test_setup_drops_the_entities_earlier_versions_created(hass):
    """Entities this version no longer creates must not linger as orphans."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    coordinator = _make_coordinator()
    coordinator.device_mac = "11:22:33:44:55:66"
    registry = er.async_get(hass)
    retired = [
        registry.async_get_or_create("select", DOMAIN, "11:22:33:44:55:66_zone_select", config_entry=entry),
        registry.async_get_or_create("number", DOMAIN, "11:22:33:44:55:66_cutting_height", config_entry=entry),
        registry.async_get_or_create("camera", DOMAIN, f"{entry.entry_id}_map_camera", config_entry=entry),
        registry.async_get_or_create("camera", DOMAIN, "11:22:33:44:55:66_map_camera", config_entry=entry),
    ]
    kept = registry.async_get_or_create("sensor", DOMAIN, "11:22:33:44:55:66_battery", config_entry=entry)

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ) as forward_entry_setups:
        assert await async_setup_entry(hass, entry) is True

    assert all(registry.async_get(entity.entity_id) is None for entity in retired)
    assert registry.async_get(kept.entity_id) is not None
    platforms = forward_entry_setups.await_args.args[1]
    assert not {Platform.CAMERA, Platform.BUTTON, Platform.NUMBER} & set(platforms)


async def test_async_setup_entry_reads_the_preferences_of_fixed_height_models(hass):
    """A model with a manual height dial still keeps the other mowing settings."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = _make_coordinator()
    coordinator.supports_cutting_height = False

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(return_value=None),
    ):
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_fetch_mowing_preferences.assert_awaited_once()


async def test_async_setup_entry_raises_not_ready_on_connect_failure(hass):
    """A failed device connection should raise ConfigEntryNotReady so HA retries."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.device_type = "mower"
    coordinator.name = "Test Mower"
    coordinator.async_connect_device = AsyncMock(return_value=False)
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)

    with patch(
        "custom_components.dreame_mower.DreameMowerCoordinator",
        return_value=coordinator,
    ), pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    coordinator.async_connect_device.assert_awaited_once()
    coordinator.async_config_entry_first_refresh.assert_not_awaited()
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data.get(DOMAIN, {})

async def _setup_with_callbacks(hass, coordinator) -> list:
    """Run setup with a stubbed coordinator and return the registered poll callbacks."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ), patch(
        "custom_components.dreame_mower.async_track_time_interval"
    ) as track_time_interval:
        assert await async_setup_entry(hass, entry) is True

    return [call.args[1] for call in track_time_interval.call_args_list]


async def _setup_with(hass, coordinator):
    """Run setup with a stubbed coordinator and report the registered intervals."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ), patch(
        "custom_components.dreame_mower.async_track_time_interval"
    ) as track_time_interval:
        assert await async_setup_entry(hass, entry) is True

    return [call.args[2] for call in track_time_interval.call_args_list]


async def test_async_setup_entry_polls_the_rain_state(hass):
    """Neither the settings nor the resume time are pushed, so setup has to poll."""
    intervals = await _setup_with(hass, _make_coordinator())

    assert timedelta(seconds=RAIN_POLL_INTERVAL_SECONDS) in intervals


async def test_rain_poll_is_set_up_before_rain_protection_is_known(hass):
    """Whether the mower offers rain protection is read only after setup."""
    coordinator = _make_coordinator()
    coordinator.supports_rain_protection = False

    async def read_settings() -> None:
        coordinator.supports_rain_protection = True

    coordinator.async_fetch_device_settings = AsyncMock(side_effect=read_settings)
    callbacks = await _setup_with_callbacks(hass, coordinator)
    await hass.async_block_till_done()
    rain_poll = next(cb for cb in callbacks if cb.__name__ == "_async_poll_rain")

    await rain_poll()
    coordinator.async_fetch_rain_protection_end.assert_awaited_once()


async def test_rain_poll_asks_nothing_of_a_mower_without_rain_protection(hass):
    coordinator = _make_coordinator()
    coordinator.supports_rain_protection = False
    callbacks = await _setup_with_callbacks(hass, coordinator)
    rain_poll = next(cb for cb in callbacks if cb.__name__ == "_async_poll_rain")

    await rain_poll()

    coordinator.async_fetch_rain_protection_end.assert_not_awaited()


async def test_async_setup_entry_skips_the_settings_fetch_for_swbot(hass):
    """Sweeping robots keep none of the settings this record carries."""
    coordinator = _make_coordinator()
    coordinator.device_type = DEVICE_TYPE_SWBOT
    coordinator.supports_rain_protection = False

    await _setup_with(hass, coordinator)

    coordinator.async_fetch_device_settings.assert_not_awaited()


async def test_async_setup_entry_polls_the_schedules(hass):
    """A changed schedule is the one thing the device does not announce."""
    intervals = await _setup_with(hass, _make_coordinator())

    assert timedelta(seconds=SCHEDULE_POLL_INTERVAL_SECONDS) in intervals


async def test_async_setup_entry_polls_the_schedules_after_a_failed_read(hass):
    """The poll is what recovers a mower that was unreachable at startup.

    Gating it on the startup read would leave the schedules unread until the user
    reloaded the integration by hand.
    """
    coordinator = _make_coordinator()
    coordinator.supports_schedules = False
    coordinator.async_fetch_schedules = AsyncMock(side_effect=Exception("device asleep"))

    intervals = await _setup_with(hass, coordinator)

    assert timedelta(seconds=SCHEDULE_POLL_INTERVAL_SECONDS) in intervals


async def test_async_setup_entry_skips_the_schedule_fetch_for_swbot(hass):
    """Sweeping robots keep no schedules to read."""
    coordinator = _make_coordinator()
    coordinator.device_type = DEVICE_TYPE_SWBOT
    coordinator.supports_rain_protection = False
    coordinator.supports_schedules = False

    await _setup_with(hass, coordinator)

    coordinator.async_fetch_schedules.assert_not_awaited()


async def test_async_setup_entry_polls_the_maps(hass):
    """An edited or deleted map is not announced, so setup has to poll for it."""
    coordinator = _make_coordinator()
    coordinator.device.refresh_changed_vector_map = MagicMock(return_value=False)
    callbacks = await _setup_with_callbacks(hass, coordinator)

    for callback in callbacks:
        await callback()

    coordinator.device.refresh_changed_vector_map.assert_called_once_with()


async def test_async_setup_entry_skips_the_map_poll_for_swbot(hass):
    """Sweeping robots keep no mower maps to check."""
    coordinator = _make_coordinator()
    coordinator.device_type = DEVICE_TYPE_SWBOT
    coordinator.supports_rain_protection = False
    coordinator.device.refresh_changed_vector_map = MagicMock(return_value=False)
    callbacks = await _setup_with_callbacks(hass, coordinator)

    for callback in callbacks:
        await callback()

    coordinator.device.refresh_changed_vector_map.assert_not_called()



async def test_offline_mower_skips_the_reads_it_cannot_answer(hass):
    """Commands to a mower the cloud reports offline only time out."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    coordinator = _make_coordinator()
    coordinator.device.async_check_reachable = AsyncMock(return_value=False)
    coordinator.reload_when_online = False

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ):
        assert await async_setup_entry(hass, entry) is True

    # The maps come from the cloud's copy; nothing asks the mower itself.
    coordinator.device.load_stored_vector_map.assert_called_once_with()
    coordinator.device.fetch_vector_map.assert_not_called()
    coordinator.async_refresh_map_extras.assert_not_awaited()
    coordinator.async_fetch_consumable_data.assert_not_awaited()
    coordinator.async_fetch_mowing_preferences.assert_not_awaited()
    coordinator.async_fetch_device_settings.assert_not_awaited()
    coordinator.async_fetch_schedules.assert_not_awaited()
    assert coordinator.reload_when_online is True


async def test_setup_does_not_wait_for_the_device_reads(hass):
    """Setup finishes while the reads that decide what the mower offers still run."""
    import asyncio

    entry = _make_entry()
    entry.add_to_hass(hass)
    coordinator = _make_coordinator()
    release = asyncio.Event()

    async def slow_read() -> bool:
        await release.wait()
        return True

    coordinator.async_fetch_mowing_preferences = AsyncMock(side_effect=slow_read)

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ) as forward:
        assert await async_setup_entry(hass, entry) is True

        forward.assert_awaited_once()
        coordinator.async_mark_probed.assert_not_called()

        release.set()
        await hass.async_block_till_done()

    coordinator.async_mark_probed.assert_called_once_with()


async def test_offline_mower_is_probed_at_once(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)
    coordinator = _make_coordinator()
    coordinator.device.async_check_reachable = AsyncMock(return_value=False)

    with patch("custom_components.dreame_mower.DreameMowerCoordinator", return_value=coordinator), patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ):
        assert await async_setup_entry(hass, entry) is True

    coordinator.async_mark_probed.assert_called_once_with()
    coordinator.async_fetch_mowing_preferences.assert_not_awaited()


async def test_robot_without_a_lawn_is_probed_at_once(hass):
    coordinator = _make_coordinator()
    coordinator.device_type = DEVICE_TYPE_SWBOT

    await _setup_with(hass, coordinator)

    coordinator.async_mark_probed.assert_called_once_with()


async def test_unloading_drops_entities_still_waiting_for_the_reads(hass):
    from custom_components.dreame_mower import async_unload_entry
    from custom_components.dreame_mower.const import DATA_PLATFORMS

    entry = _make_entry()
    entry.add_to_hass(hass)
    coordinator = _make_coordinator()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator, DATA_PLATFORMS: []}

    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
        assert await async_unload_entry(hass, entry) is True

    coordinator.async_cancel_probe.assert_called_once_with()
