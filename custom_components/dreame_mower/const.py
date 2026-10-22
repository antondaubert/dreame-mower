"""Constants for the Dreame Mower integration."""

from __future__ import annotations
from typing import Final

DOMAIN = "dreame_mower"

# Configuration constants
CONF_NOTIFY: Final = "notify"
CONF_MAP_ROTATION: Final = "map_rotation"

DEFAULT_MAP_ROTATION: Final = 0

# Data storage keys
DATA_COORDINATOR = "coordinator"
DATA_PLATFORMS = "platforms"
DATA_POINT_CLOUD = "point_cloud"

# How often to poll the cloud for firmware update availability.
FIRMWARE_POLL_INTERVAL_HOURS = 24

# How often to poll the cloud connectivity heartbeat to detect whether the
# device itself is online. The cloud MQTT link the integration uses stays up
# even when the robot loses its own connection, so this poll is what flips
# entities to unavailable while the device is offline.
ONLINE_POLL_INTERVAL_SECONDS = 60

# How often to re-read the time rain protection lets the mower work again. The
# device reports that time when it starts holding the mower back but says
# nothing when it simply runs out, so the poll is what retires a time that has
# passed. Settings are not polled: the device announces every change to those.
RAIN_POLL_INTERVAL_SECONDS = 300

# How often to check whether the schedules changed. A changed schedule is the one
# thing the device does not announce, and asking for the version it holds them
# under is a single command, so the schedules themselves are only read back once
# that version moved.
SCHEDULE_POLL_INTERVAL_SECONDS = 900

# How often to check whether a map changed. An edited map is not announced
# either, and its hash is a single command per map, so the maps themselves are
# only read back once a hash moved.
MAP_POLL_INTERVAL_SECONDS = 900