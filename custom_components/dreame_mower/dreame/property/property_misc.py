"""Miscellaneous property handlers for known but not actively used properties.

This module provides simple logging handlers for properties that are known
but not currently useful for the integration. These handlers log the data
for observability without extracting specific values.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from ..const import PROPERTY_1_1, SETTINGS_CHANGE_PROPERTY

# Heartbeat (prop 1:1) decoded constants
_MAIN_STATE_MOWING = 4
PROPERTY_1_1_TASK_STATUS_NAME = "property_1_1_task_status"
PROPERTY_1_1_ACTIVE_CODES_NAME = "property_1_1_active_codes"
SETTINGS_CHANGED_PROPERTY_NAME = "device_settings_changed"

# The heartbeat carries the codes the device currently reports as a bitmask in
# bytes 1 to 10: bit N of byte i stands for code i * 8 + N, the same numbering
# the device code property (2:2) uses. Unlike that property, which announces a
# code once as it happens, the bitmask is live state — a bit stays set for as
# long as the condition holds and clears on its own once it no longer does.
_ACTIVE_CODE_BITMASK_START = 1
_ACTIVE_CODE_BITMASK_END = 11
_BITS_PER_BYTE = 8
# Bit 79 is set in every heartbeat regardless of what the device reports, so it
# carries no condition and is left out.
_ACTIVE_CODE_SENTINEL_BIT = 79

# Mowing task status decoded from the heartbeat byte 13 (subState). The raw byte
# encodes the task status as (subState - base); the resulting index maps to the
# task-status enum below. The status is only meaningful while the main state is
# "mowing"; in any other main state there is no active mowing task ("idle").
#
# "returning_to_dock" is a transient state the robot passes through while driving
# back to the dock — both after completing a run (finished → returning_to_dock →
# exit → idle) and after an interruption (mowing → returning_to_dock → paused).
# An interrupted task comes to rest at "paused", which is the resumable state.
_TASK_STATUS_SUBSTATE_BASE = 33
_TASK_STATUS_BY_INDEX: dict[int, str] = {
    0: "idle",
    1: "starting",
    2: "mowing",
    3: "paused",
    4: "finished",
    5: "failed",
    6: "exit",
    7: "returning_to_dock",
}
# Ordered tuple of every possible task-status value, for sensor enum options.
TASK_STATUS_OPTIONS: tuple[str, ...] = tuple(_TASK_STATUS_BY_INDEX.values())

# Task statuses that mean no mowing session is in progress. Every other decoded
# status (starting/mowing/paused/finished/failed/returning_to_dock) means a
# session is active and the live map should keep running — including while the
# task is paused at the dock. The session only ends at "exit"/"idle".
_INACTIVE_TASK_STATUSES = frozenset({"idle", "exit"})

_LOGGER = logging.getLogger(__name__)


class Property11Handler:
    """Handler for property 1:1 - complex status/telemetry data.
    
    This property contains 20-byte array with various telemetry including:
    - Raw battery charging state (byte 10: 0-100 direct %, ≥128 means charging with value-128)
    
    Currently only logged for observability, not actively used in integration.
    """
    
    def __init__(self) -> None:
        """Initialize property handler."""
        self._last_value: list[int] | None = None
        self._task_status: str | None = None
        self._active_codes: frozenset[int] | None = None

    def parse_value(self, value: list[int], notify_callback: Callable[[str, Any], None] | None = None) -> bool:
        """Parse and log property 1:1 value."""
        try:
            if not isinstance(value, list):
                _LOGGER.warning("Property 1:1 unexpected type: %s, value: %s", type(value), value)
                return False

            self._last_value = value.copy()

            # Known format: 20-byte array with sentinel 0xCE at positions 0 and 19
            if len(value) == 20 and value[0] == 206 and value[19] == 206:
                raw_battery = value[11]  # byte 11: raw battery state with charging flag
                main_state = (value[12] & 0x0F) - 1  # byte 12: (mainState+1) | (seq<<4)
                sub_state = value[13]  # byte 13: subState
                _LOGGER.debug(
                    "Property 1:1 received - raw_battery: %d, main_state: %d, sub_state: %d",
                    raw_battery, main_state, sub_state,
                )
                self._update_task_status(main_state, sub_state, notify_callback)
                self._update_active_codes(value, notify_callback)
            elif len(value) == 24:
                # 24-byte variant seen on mova.mower.g2405c firmware 4.3.6_0062 (issue #18)
                _LOGGER.debug("Property 1:1 received (24-byte variant): %s", value)
            elif len(value) == 22:
                # 22-byte variant seen on dreame.mower.a3-awd-pro (issue #178)
                _LOGGER.debug("Property 1:1 received (22-byte variant): %s", value)
            elif len(value) == 20:
                # 20-byte variant with non-CE sentinels seen on dreame.swbot.g2509 fw 4.3.6_0603
                _LOGGER.debug("Property 1:1 received (20-byte alt-sentinel variant): %s", value)
            else:
                _LOGGER.warning("Property 1:1 unrecognised format (len=%d): %s", len(value), value)
                return False

            return True

        except Exception as ex:
            _LOGGER.error("Failed to parse property 1:1: %s", ex)
            return False

    def _update_task_status(
        self,
        main_state: int,
        sub_state: int,
        notify_callback: Callable[[str, Any], None] | None,
    ) -> None:
        """Update the decoded task status and derived resumable flag, notifying on change."""
        if main_state == _MAIN_STATE_MOWING:
            status = _TASK_STATUS_BY_INDEX.get(sub_state - _TASK_STATUS_SUBSTATE_BASE)
        else:
            # No mowing task in progress in any other main state.
            status = "idle"
        if status != self._task_status:
            self._task_status = status
            if notify_callback is not None:
                notify_callback(PROPERTY_1_1_TASK_STATUS_NAME, status)

    @staticmethod
    def _decode_active_codes(value: list[int]) -> frozenset[int]:
        """Decode the codes the heartbeat currently reports as set."""
        active_codes = set()
        bitmask = value[_ACTIVE_CODE_BITMASK_START:_ACTIVE_CODE_BITMASK_END]
        for byte_index, byte in enumerate(bitmask):
            for bit in range(_BITS_PER_BYTE):
                if byte & (1 << bit):
                    code = byte_index * _BITS_PER_BYTE + bit
                    if code != _ACTIVE_CODE_SENTINEL_BIT:
                        active_codes.add(code)
        return frozenset(active_codes)

    def _update_active_codes(
        self,
        value: list[int],
        notify_callback: Callable[[str, Any], None] | None,
    ) -> None:
        """Update the codes the device currently reports, notifying on change."""
        active_codes = self._decode_active_codes(value)
        if active_codes == self._active_codes:
            return

        _LOGGER.debug(
            "Heartbeat active codes changed: %s -> %s",
            sorted(self._active_codes) if self._active_codes is not None else None,
            sorted(active_codes),
        )
        self._active_codes = active_codes
        if notify_callback is not None:
            notify_callback(PROPERTY_1_1_ACTIVE_CODES_NAME, active_codes)

    @property
    def active_codes(self) -> frozenset[int] | None:
        """Return the codes the device currently reports (None until a heartbeat is seen)."""
        return self._active_codes

    @property
    def task_status(self) -> str | None:
        """Return the decoded mowing task status (None until a heartbeat is seen)."""
        return self._task_status

    @property
    def mowing_session_active(self) -> bool:
        """Return True while a mowing session is in progress (drives the live map)."""
        return (
            self._task_status is not None
            and self._task_status not in _INACTIVE_TASK_STATUSES
        )

    @property
    def last_value(self) -> list[int] | None:
        """Return last received property value."""
        return self._last_value.copy() if self._last_value else None


class SettingsChangeHandler:
    """Handler for generic settings change acknowledgment property (2:51).

    The device announces every settings change here, whoever made it. The value
    it carries is the changed setting on its own, without anything naming which
    setting that is — a bare list of numbers is as consistent with the rain
    settings as with the do-not-disturb window. It therefore only says *that*
    something changed, which is the cue to read the settings record back.
    """

    def __init__(self) -> None:
        """Initialize settings change handler."""
        self._last_value: dict[str, Any] | None = None

    def parse_value(
        self,
        value: Any,
        notify_callback: Callable[[str, Any], None] | None = None,
    ) -> bool:
        """Parse a settings change acknowledgment and announce it."""
        try:
            if not isinstance(value, dict):
                _LOGGER.warning("Invalid settings change value type: %s, value: %s", type(value), value)
                return False

            self._last_value = value

            # Log the settings change as info with JSON content
            _LOGGER.info("Settings change acknowledged (2:51): %s", json.dumps(value))
            if notify_callback is not None:
                notify_callback(SETTINGS_CHANGED_PROPERTY_NAME, value)
            return True

        except Exception as ex:
            _LOGGER.error("Failed to parse settings change acknowledgment: %s, value: %s", ex, value)
            return False
    
    @property
    def last_value(self) -> dict[str, Any] | None:
        """Return last received settings change data."""
        return self._last_value.copy() if self._last_value else None


class MiscPropertyHandler:
    """Unified handler for all miscellaneous properties."""
    
    def __init__(self) -> None:
        """Initialize misc property handler."""
        self._property_1_1_handler = Property11Handler()
        self._settings_change_handler = SettingsChangeHandler()
    
    @staticmethod
    def matches(siid: int, piid: int) -> bool:
        """Check if a property is a miscellaneous property."""
        return PROPERTY_1_1.matches(siid, piid) or SETTINGS_CHANGE_PROPERTY.matches(siid, piid)
    
    @property
    def task_status(self) -> str | None:
        """Return the decoded mowing task status from the heartbeat."""
        return self._property_1_1_handler.task_status

    @property
    def mowing_session_active(self) -> bool:
        """Return True while a mowing session is in progress."""
        return self._property_1_1_handler.mowing_session_active

    @property
    def active_codes(self) -> frozenset[int] | None:
        """Return the codes the device currently reports in its heartbeat."""
        return self._property_1_1_handler.active_codes

    def handle_property_update(self, siid: int, piid: int, value: Any, notify_callback: Callable[[str, Any], None]) -> bool:
        """Handle miscellaneous property updates."""
        try:
            if PROPERTY_1_1.matches(siid, piid):
                return self._property_1_1_handler.parse_value(value, notify_callback)
            elif SETTINGS_CHANGE_PROPERTY.matches(siid, piid):
                return self._settings_change_handler.parse_value(value, notify_callback)
            else:
                # Property not handled by this handler
                return False
                
        except Exception as ex:
            _LOGGER.error("Failed to handle misc property %d:%d:%s: %s", siid, piid, value, ex)
            return False
