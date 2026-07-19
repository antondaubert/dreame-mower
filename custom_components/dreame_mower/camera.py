from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from threading import Timer

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN, CONF_MAP_ROTATION, CONF_MAP_SHOW_TITLE, CONF_MAP_SHOW_LEGEND, CONF_MAP_PADDING
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

from .dreame.const import POSE_COVERAGE_PROPERTY
from .dreame.property.pose_coverage import POSE_COVERAGE_COORDINATES_PROPERTY_NAME
from .dreame.property.property_misc import PROPERTY_1_1_TASK_STATUS_NAME
from .dreame.map_data_parser import vector_map_to_map_data
from .dreame.svg_map_generator import generate_svg_map_image

_LOGGER = logging.getLogger(__name__)

# Pose coverage property request interval during live mowing sessions
POSE_COVERAGE_REQUEST_INTERVAL = 120  # 2 minutes in seconds


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dreame Mower camera."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    
    camera = DreameMowerCameraEntity(coordinator, entry)
    async_add_entities([camera], True)


class DreameMowerCameraEntity(DreameMowerEntity, Camera):
    """Camera entity for Dreame Mower map visualization."""

    def __init__(self, coordinator: DreameMowerCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the camera."""
        # Initialize base entity with a suitable key
        DreameMowerEntity.__init__(self, coordinator, "map_camera")
        Camera.__init__(self)
        
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_map_camera"
        self._attr_translation_key = "map_camera"
        self._attr_supported_features = CameraEntityFeature.ON_OFF
        
        # Set content type for SVG images
        self.content_type = "image/svg+xml"
        
        # Current map data
        self._current_map_data: dict[str, Any] | None = None
        self._historical_file_path: str | None = None
        self._image_bytes: bytes | None = None
        self._is_on = True

        # Live mode state
        self._live_coordinates: list[list[int]] = []  # [x, y] pairs in map units
        
        # Periodic property request timer for live mode
        self._pose_coverage_timer: Timer | None = None
        self._timer_interval = POSE_COVERAGE_REQUEST_INTERVAL

        # Live mode follows the mowing task lifecycle (heartbeat task status),
        # not the physical dock/charge state — so a task paused at the dock keeps
        # the live map running. None until the first heartbeat arrives.
        self._session_active = coordinator.device.mowing_session_active
        
        # Historical files cache
        self._historical_files_cache: list[tuple[str, float]] = []  # [(file_path, mtime), ...]
        self._cache_built = False
        
        # Track current rotation to detect changes
        self._current_rotation = self.config_entry.options.get(CONF_MAP_ROTATION, 0)
        self._current_show_title = self.config_entry.options.get(CONF_MAP_SHOW_TITLE, True)
        self._current_show_legend = self.config_entry.options.get(CONF_MAP_SHOW_LEGEND, True)
        self._current_padding = self.config_entry.options.get(CONF_MAP_PADDING, 50)
        
        # Register for property change notifications
        self.coordinator.device.register_property_callback(self._handle_property_change)

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        # Build historical files cache first, then render from historical data
        # or fall back to batch API vector map
        self.hass.create_task(self._async_initial_image_load())

        # If a mowing session is active, request initial pose coverage and start timer
        if self._session_active:
            await self._request_pose_coverage_property()
            self._start_pose_coverage_timer()
        
        # Listen for config entry options updates
        self.async_on_remove(
            self.config_entry.add_update_listener(self._async_config_entry_updated)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity is being removed from Home Assistant."""
        # Ensure timer is stopped and cleaned up
        self._stop_pose_coverage_timer()
        await super().async_will_remove_from_hass()

    async def _async_initial_image_load(self) -> None:
        """Load initial image: prefer historical files, fall back to batch API vector map.

        Always fetches vector map in the background so it's available for live mode,
        since live pose coordinates use the same coordinate system as the vector map
        but a different (lower-resolution) system than historical data.
        """
        await self._refresh_historical_files_cache()
        if self._historical_files_cache:
            await self._async_update_image()
            # Also fetch vector map for live mode (don't await — non-blocking)
            self.hass.create_task(self._async_fetch_vector_map_silent())
        else:
            await self._async_fetch_vector_map()

    async def _async_fetch_vector_map(self) -> None:
        """Fetch vector map data from batch API and render it as the camera image."""
        try:
            loop = asyncio.get_event_loop()
            updated = await loop.run_in_executor(
                None, self.coordinator.device.fetch_vector_map
            )
            if updated:
                await self._async_update_vector_map_image()
        except Exception as ex:
            _LOGGER.warning("Failed to fetch vector map: %s", ex)

    async def _async_fetch_vector_map_silent(self) -> None:
        """Fetch vector map data from batch API without rendering.

        Used when historical data is already displayed but we need the vector
        map cached for live mode coordinate matching.
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self.coordinator.device.fetch_vector_map
            )
        except Exception as ex:
            _LOGGER.warning("Failed to fetch vector map: %s", ex)

    async def _async_config_entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle config entry options update."""
        new_rotation = entry.options.get(CONF_MAP_ROTATION, 0)
        new_show_title = entry.options.get(CONF_MAP_SHOW_TITLE, True)
        new_show_legend = entry.options.get(CONF_MAP_SHOW_LEGEND, True)
        new_padding = entry.options.get(CONF_MAP_PADDING, 50)
        changed = (
            new_rotation != self._current_rotation
            or new_show_title != self._current_show_title
            or new_show_legend != self._current_show_legend
            or new_padding != self._current_padding
        )
        self._current_rotation = new_rotation
        self._current_show_title = new_show_title
        self._current_show_legend = new_show_legend
        self._current_padding = new_padding
        if changed:
            # Re-render the image with new settings
            if self._is_on:
                if self._live_coordinates:
                    # Re-render live image
                    await self._async_update_live_image()
                else:
                    # Re-render static map
                    await self._async_update_image()
                self.async_write_ha_state()

    async def _request_pose_coverage_property(self) -> None:
        """Request POSE_COVERAGE_PROPERTY from device to maintain live data stream.
        
        During live mowing sessions, the device stops sending pose coverage updates
        after POSE_COVERAGE_REQUEST_INTERVAL if not requested. This method keeps the data
        flowing.
        """
        # Don't request if device is not connected or not reachable
        if not self.coordinator.device_connected or not self.coordinator.device.device_reachable:
            return

        try:
            parameters = [{
                "siid": POSE_COVERAGE_PROPERTY.siid,
                "piid": POSE_COVERAGE_PROPERTY.piid
            }]
            # Run the blocking HTTP call in an executor to avoid blocking the event loop
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.coordinator.device.cloud_device.get_properties(parameters, retry_count=1)
            )
        except TimeoutError:
            # Device offline - stop timer to avoid spamming
            # The timer will be restarted when device becomes reachable again (via property update)
            _LOGGER.warning("Device offline, pausing pose coverage requests")
            self._stop_pose_coverage_timer()
        except Exception as ex:
            _LOGGER.warning("Failed to request pose coverage property: %s", ex)

    def _start_pose_coverage_timer(self) -> None:
        """Start periodic timer to request pose coverage property during live mowing."""
        if self._pose_coverage_timer is not None:
            self._pose_coverage_timer.cancel()
        
        self._pose_coverage_timer = Timer(self._timer_interval, self._pose_coverage_timer_callback)
        self._pose_coverage_timer.start()

    def _stop_pose_coverage_timer(self) -> None:
        """Stop periodic timer for pose coverage property requests."""
        if self._pose_coverage_timer is not None:
            self._pose_coverage_timer.cancel()
            self._pose_coverage_timer = None

    def _pose_coverage_timer_callback(self) -> None:
        """Timer callback to request pose coverage property and schedule next request."""
        try:
            # Schedule the async property request as a task
            self.hass.create_task(self._request_pose_coverage_property())
            
            # Schedule next request while the mowing session is still active
            if self._session_active:
                self._start_pose_coverage_timer()
        except Exception as ex:
            _LOGGER.error("Error in pose coverage timer callback: %s", ex)

    async def _refresh_historical_files_cache(self) -> None:
        """Refresh the historical files cache by scanning the ali_dreame directory."""
        try:
            loop = asyncio.get_event_loop()
            self._historical_files_cache = await loop.run_in_executor(
                None, self._build_historical_files_list_sync
            )
            self._cache_built = True
        except Exception as ex:
            _LOGGER.error("Failed to refresh historical files cache: %s", ex)
            self._historical_files_cache = []
            self._cache_built = True

    def _build_historical_files_list_sync(self) -> list[tuple[str, float]]:
        """Build the historical files list synchronously (runs in executor).
        
        Only includes files whose name starts with this device's ID
        (format: ``{device_id}_{timestamp}.json``).

        Returns:
            List of (file_path, mtime) tuples sorted by modification time (newest first)
        """
        try:
            ali_dreame_path = os.path.join(
                self.hass.config.config_dir,
                "www",
                "dreame",
                "ali_dreame"
            )
            
            if not os.path.exists(ali_dreame_path):
                return []
            
            device_id = self.coordinator.device.device_id
            prefix = f"{device_id}_"

            # Find .json files belonging to this device
            json_files = []
            for root, dirs, files in os.walk(ali_dreame_path):
                for file in files:
                    if file.endswith('.json') and file.startswith(prefix):
                        full_path = os.path.join(root, file)
                        try:
                            # Get file modification time
                            mtime = os.path.getmtime(full_path)
                            json_files.append((full_path, mtime))
                        except OSError as ex:
                            _LOGGER.warning("Could not stat file %s: %s", full_path, ex)
                            continue  # Skip files we can't stat
            
            # Sort by modification time (newest first)
            json_files.sort(key=lambda x: x[1], reverse=True)
            return json_files
            
        except Exception as ex:
            _LOGGER.error("Error building historical files list: %s", ex)
            return []

    def _handle_property_change(self, property_name: str, value: Any) -> None:
        """Handle property changes from the device."""
        # If device is reachable and a session is active but the timer is stopped,
        # restart it. This handles recovery from an offline state.
        if (self.coordinator.device.device_reachable and
            self._session_active and
            self._pose_coverage_timer is None):
            _LOGGER.info("Device is back online, resuming pose coverage requests")
            self._start_pose_coverage_timer()

        if property_name == "vector_map_updated":
            # Vector map data was fetched — re-render if we have no historical data
            if not self._current_map_data and self._is_on:
                self.hass.create_task(self._async_update_vector_map_image())
        elif property_name == POSE_COVERAGE_COORDINATES_PROPERTY_NAME:
            self._handle_live_coordinates_update(value)
        elif property_name == PROPERTY_1_1_TASK_STATUS_NAME:
            # Live map follows the task lifecycle: it runs while a session is
            # active (incl. paused at the dock) and ends only at exit/idle.
            new_state = self.coordinator.device.mowing_session_active
            if new_state != self._session_active:
                self._session_active = new_state
                if new_state:
                    # Session started or resumed — enter live mode.
                    self._start_pose_coverage_timer()
                else:
                    # Session ended — stop timer, clear coordinates, show static map.
                    self._stop_pose_coverage_timer()
                    self._live_coordinates.clear()
                    self.hass.create_task(self._async_update_image(force_refresh=True))

    def _handle_live_coordinates_update(self, coordinates_data: dict[str, Any]) -> None:
        """Handle live coordinate updates during mowing session.

        Coordinates are now in map units (same as zone data) after 20-bit
        pose parsing with *10 scaling.  Track points from pose coverage
        deltas are also included.
        """
        try:
            x = coordinates_data.get('x')
            y = coordinates_data.get('y')

            # Append robot position as [x, y]
            if x is not None and y is not None:
                self._live_coordinates.append([int(x), int(y)])
            
            # Limit live coordinates to last 2000 points to avoid memory issues
            if len(self._live_coordinates) > 2000:
                self._live_coordinates = self._live_coordinates[-2000:]
            
            # Update image with new live data
            if self._is_on:
                self.hass.create_task(self._async_update_live_image())
                            
        except Exception as ex:
            _LOGGER.error("Error handling live coordinates update: %s", ex)

    async def _async_update_live_image(self) -> None:
        """Update camera image with live coordinates overlay."""
        if not self._live_coordinates:
            return
            
        try:
            # Generate live image in executor
            loop = asyncio.get_event_loop()
            self._image_bytes = await loop.run_in_executor(
                None,
                self._generate_live_image
            )
            
        except Exception as ex:
            _LOGGER.error("Failed to update live image: %s", ex)

    def _generate_live_image(self) -> bytes:
        """Generate live map image in SVG format with current coordinates overlay on vector map."""
        assert self.coordinator.device.vector_map is not None
        map_data = vector_map_to_map_data(self.coordinator.device.vector_map)

        return generate_svg_map_image(
            map_data, None, self.coordinator,
            rotation=self._current_rotation,
            live_coordinates=self._live_coordinates,
            show_title=self._current_show_title,
            show_legend=self._current_show_legend,
            padding=self._current_padding,
        )

    @property
    def is_on(self) -> bool:
        """Return True if the camera is on."""
        return self._is_on

    async def async_turn_on(self) -> None:
        """Turn on the camera."""
        self._is_on = True
        await self._async_update_image()

    async def async_turn_off(self) -> None:
        """Turn off the camera."""
        self._is_on = False
        self._image_bytes = None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return camera image bytes."""
        return self._image_bytes

    async def async_update(self) -> None:
        """Update the camera with latest map data.
        
        Image updates are primarily handled by event-driven property callbacks,
        but this method provides a fallback to ensure an image is always available.
        """
        if not self._image_bytes:
            await self._async_update_image()



    def _load_historical_file_sync(self, full_path: str) -> dict[str, Any] | None:
        """Synchronously load historical file - runs in executor."""
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as ex:
            _LOGGER.error("Error reading historical file %s: %s", full_path, ex)
            return None

    async def _find_most_recent_historical_file(self, force_refresh: bool = False) -> str | None:
        """Find the most recent historical file using the cached file list.
        
        Returns:
            Full path to the most recent .json file, or None if none found
        """
        try:
            # Build cache if not built yet
            if not self._cache_built or force_refresh:
                await self._refresh_historical_files_cache()
            
            # Return the most recent file from cache
            if self._historical_files_cache:
                return self._historical_files_cache[0][0]  # First item is most recent
            else:
                return None
                
        except Exception as ex:
            _LOGGER.error("Error getting most recent historical file from cache: %s", ex)
            return None

    async def _async_update_vector_map_image(self) -> None:
        """Update camera image using vector map data from batch API."""
        vector_map = self.coordinator.device.vector_map
        if not vector_map or not vector_map.boundary:
            return

        try:
            data = vector_map_to_map_data(vector_map)
            loop = asyncio.get_event_loop()
            self._image_bytes = await loop.run_in_executor(
                None,
                self._generate_map_image,
                data,
            )
        except Exception as ex:
            _LOGGER.error("Failed to generate vector map image: %s", ex)

    async def _async_update_image(self, force_refresh: bool = False) -> None:
        """Update the camera image by generating a new map visualization."""

        historical_file = await self._find_most_recent_historical_file(force_refresh=force_refresh)
        if not historical_file:
            # No historical files — try vector map from batch API
            await self._async_update_vector_map_image()
            return

        try:
            # Load historical file directly (we already have the full path)
            loop = asyncio.get_event_loop()
            self._current_map_data = await loop.run_in_executor(
                None,
                self._load_historical_file_sync,
                historical_file
            )
            if self._current_map_data is None:
                _LOGGER.warning("Failed to load historical file data: %s", historical_file)
                return
            
            # Set relative path for display purposes
            www_dreame_path = os.path.join(self.hass.config.config_dir, "www", "dreame")
            if historical_file.startswith(www_dreame_path):
                self._historical_file_path = os.path.relpath(historical_file, www_dreame_path)
            else:
                self._historical_file_path = os.path.basename(historical_file)

        except Exception as ex:
            _LOGGER.warning("Could not load historical file %s: %s", historical_file, ex)
            return
                    
        try:
            # Generate the map image in an executor to avoid blocking (including module loading)
            loop = asyncio.get_event_loop()
            self._image_bytes = await loop.run_in_executor(
                None, 
                self._generate_map_image,
                self._current_map_data
            )
        except Exception as ex:
            _LOGGER.error("Failed to generate map image: %s", ex)

    def _generate_map_image(self, data: dict[str, Any]) -> bytes:
        """Generate map image in SVG format from map data."""
        return generate_svg_map_image(
            data, self._historical_file_path, self.coordinator,
            rotation=self._current_rotation,
            show_title=self._current_show_title,
            show_legend=self._current_show_legend,
            padding=self._current_padding,
        )

    @property
    def available(self) -> bool:
        """Return True if the camera is available."""
        return self.coordinator.device_connected and self.coordinator.device_online