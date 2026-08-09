"""Constants for the Dreame Mower integration."""

from __future__ import annotations
from typing import Final

DOMAIN = "dreame_mower"

# Configuration constants
CONF_NOTIFY: Final = "notify"
CONF_MAP_ROTATION: Final = "map_rotation"
CONF_MAP_SHOW_TITLE: Final = "map_show_title"
CONF_MAP_SHOW_LEGEND: Final = "map_show_legend"
CONF_MAP_PADDING: Final = "map_padding"

# Data storage keys
DATA_COORDINATOR = "coordinator"
DATA_PLATFORMS = "platforms"

# How often to poll the cloud for firmware update availability.
FIRMWARE_POLL_INTERVAL_HOURS = 24

# How often to poll the cloud connectivity heartbeat to detect whether the
# device itself is online. The cloud MQTT link the integration uses stays up
# even when the robot loses its own connection, so this poll is what flips
# entities to unavailable while the device is offline.
ONLINE_POLL_INTERVAL_SECONDS = 60

# How often to re-read the rain protection settings and the time rain protection
# lets the mower work again. The device pushes no update for either, so the poll
# is what expires the protection once its delay has run out and what picks up
# settings changed elsewhere.
RAIN_POLL_INTERVAL_SECONDS = 300