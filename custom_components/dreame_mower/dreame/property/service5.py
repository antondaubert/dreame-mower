"""Service 5 property handling for Dreame Mower Implementation.

This module provides parsing and handling for Service 5 properties:
- 5:100 - Unknown property (discovered in issue report)
- 5:104 - Task status (task completion status codes)
- 5:105 - Unknown property (possible capability/feature flag)
- 5:106 - BMS charging micro-phases (fine-grained charging state)
- 5:107 - Energy/discharge index (mission energy tracking)
- 5:108 - Unknown property (discovered in issue report)

These properties manage power system states, charging micro-phases, and energy consumption tracking.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from enum import Enum
from ..const import TASK_STATUS_PROPERTY, SERVICE5_PROPERTY_100, SERVICE5_PROPERTY_105, SERVICE5_PROPERTY_106, SERVICE5_ENERGY_INDEX_PROPERTY, SERVICE5_PROPERTY_108

_LOGGER = logging.getLogger(__name__)

# Property name constants for notifications
SERVICE5_PROPERTY_100_PROPERTY_NAME = SERVICE5_PROPERTY_100.name
TASK_STATUS_PROPERTY_NAME = TASK_STATUS_PROPERTY.name
SERVICE5_PROPERTY_105_PROPERTY_NAME = SERVICE5_PROPERTY_105.name
SERVICE5_PROPERTY_106_PROPERTY_NAME = SERVICE5_PROPERTY_106.name
SERVICE5_ENERGY_INDEX_PROPERTY_NAME = SERVICE5_ENERGY_INDEX_PROPERTY.name
SERVICE5_PROPERTY_108_PROPERTY_NAME = SERVICE5_PROPERTY_108.name

# Property field constants
TASK_STATUS_CODE_FIELD = "status_code"
TASK_STATUS_DESCRIPTION_FIELD = "status_description"
PROPERTY_100_VALUE_FIELD = "value_100"
PROPERTY_105_VALUE_FIELD = "value_105"
PROPERTY_106_VALUE_FIELD = "value_106"
ENERGY_INDEX_VALUE_FIELD = "energy_index"
PROPERTY_108_VALUE_FIELD = "value_108"

# Task status code mapping for property 5:104
TASK_STATUS_MAPPING: dict[int, str] = {
    7: "Task incomplete - spot mowing",
    10: "Unknown task status: 10",  # observed after LOW_BATTERY event (issue #9)
    13: "Unknown task status: 13",
}

class Service5PropertyHandler:
    """Combined handler for Service 5 properties (5:100, 5:104, 5:105, 5:106, 5:107, 5:108) with state management."""
    
    def __init__(self) -> None:
        """Initialize Service 5 property handler."""
        
        # Property 5:100 state
        self._property_100_value: int | None = None
        
        # Property 5:104 state
        self._task_status_code: int | None = None
        
        # Property 5:105 state
        self._property_105_value: int | None = None
        
        # Property 5:106 state (formerly BMS phase - purpose unclear)
        self._property_106_value: int | None = None
        
        # Property 5:107 energy index state
        self._energy_index: int | None = None
        
        # Property 5:108 state
        self._property_108_value: int | None = None
    
    def handle_property_update(self, siid: int, piid: int, value: Any, notify_callback) -> bool:
        """Handle Service 5 property update.
        
        This is the main entry point for Service 5 properties (5:100, 5:104, 5:105, 5:106, 5:107, 5:108).
        
        Args:
            siid: Service instance ID
            piid: Property instance ID  
            value: Property value from MQTT
            notify_callback: Callback function for property change notifications
            
        Returns:
            True if property was handled successfully, False otherwise
        """        
        try:
            # Handle property 5:100
            if SERVICE5_PROPERTY_100.matches(siid, piid):
                return self._handle_property_100(value, notify_callback)
            
            # Handle task status property (5:104)
            elif TASK_STATUS_PROPERTY.matches(siid, piid):
                return self._handle_task_status_property(value, notify_callback)
            
            # Handle property 5:105
            elif SERVICE5_PROPERTY_105.matches(siid, piid):
                return self._handle_property_105(value, notify_callback)
            
            # Handle property 5:106
            elif SERVICE5_PROPERTY_106.matches(siid, piid):
                return self._handle_property_106(value, notify_callback)
            
            # Handle energy index property (5:107)
            elif SERVICE5_ENERGY_INDEX_PROPERTY.matches(siid, piid):
                return self._handle_energy_index_property(value, notify_callback)
            
            # Handle property 5:108
            elif SERVICE5_PROPERTY_108.matches(siid, piid):
                return self._handle_property_108(value, notify_callback)
            
            else:
                # Not a Service 5 property
                return False
                
        except Exception as ex:
            _LOGGER.error("Failed to handle Service 5 property %d:%d: %s", siid, piid, ex)
            return False
    
    def _handle_property_100(self, value: Any, notify_callback) -> bool:
        """Handle Service 5 property 100 (purpose currently unknown, discovered via issue report)."""
        try:
            old_value = self._property_100_value
            self._property_100_value = int(value)

            property_100_data = {
                PROPERTY_100_VALUE_FIELD: self._property_100_value,
            }
            notify_callback(SERVICE5_PROPERTY_100_PROPERTY_NAME, property_100_data)

            if old_value != self._property_100_value:
                notify_callback("service5_property_100_value", self._property_100_value)

            return True

        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse Service 5 property 100 value: %s - %s", value, ex)
            return False

    def _handle_task_status_property(self, value: Any, notify_callback) -> bool:
        """Handle task status property (5:104)."""
        try:
            # Convert value to integer
            status_code = int(value)
            
            # Check if status code is in mapping
            if status_code not in TASK_STATUS_MAPPING:
                _LOGGER.warning("Unknown task status code: %s - please report this for future mapping", status_code)
                return False  # Report false to crowdsource more information
            
            old_status_code = self._task_status_code
            
            # Update state
            self._task_status_code = status_code
            
            # Get status description from mapping (or generic if unknown)
            status_description = TASK_STATUS_MAPPING[status_code]
            
            # Send notification with status code and description
            task_status_data = {
                TASK_STATUS_CODE_FIELD: status_code,
                TASK_STATUS_DESCRIPTION_FIELD: status_description,
            }
            notify_callback(TASK_STATUS_PROPERTY_NAME, task_status_data)
            
            # Notify individual state change for backward compatibility
            if old_status_code != status_code:
                notify_callback("task_status_code", status_code)
                _LOGGER.info("Task status updated: %s (%s)", status_code, status_description)
            
            return True
            
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse task status value: %s - %s", value, ex)
            return False
    
    def _handle_property_105(self, value: Any, notify_callback) -> bool:
        """Handle Service 5 property 105."""
        try:
            # Convert value to integer
            old_value = self._property_105_value
            
            # Update state
            self._property_105_value = int(value)
            
            # Send notification
            property_105_data = {
                PROPERTY_105_VALUE_FIELD: self._property_105_value,
            }
            notify_callback(SERVICE5_PROPERTY_105_PROPERTY_NAME, property_105_data)
            
            # Notify individual state change for backward compatibility
            if old_value != self._property_105_value:
                notify_callback("service5_property_105_value", self._property_105_value)

            return True
            
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse Service 5 property 105 value: %s - %s", value, ex)
            return False
    
    def _handle_property_106(self, value: Any, notify_callback) -> bool:
        """Handle Service 5 property 106 (formerly thought to be BMS charging phase)."""
        try:
            # Convert value to integer
            new_value = int(value)
            old_value = self._property_106_value
            
            # Update state
            self._property_106_value = new_value
            
            # Send notification
            property_106_data = {
                PROPERTY_106_VALUE_FIELD: new_value,
            }
            notify_callback(SERVICE5_PROPERTY_106_PROPERTY_NAME, property_106_data)
            
            # Notify individual state change for backward compatibility
            if old_value != new_value:
                notify_callback("service5_property_106_value", new_value)
            
            return True
            
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse Service 5 property 106 value: %s - %s", value, ex)
            return False
    
    def _handle_energy_index_property(self, value: Any, notify_callback) -> bool:
        """Handle energy/discharge index property (5:107)."""
        try:
            # Convert value to integer
            new_energy_index = int(value)
            old_energy_index = self._energy_index
            
            # Update state
            self._energy_index = new_energy_index
            
            # Send notification
            energy_index_data = {
                ENERGY_INDEX_VALUE_FIELD: new_energy_index,
            }
            notify_callback(SERVICE5_ENERGY_INDEX_PROPERTY_NAME, energy_index_data)
            
            # Notify individual state change for backward compatibility
            if old_energy_index != new_energy_index:
                notify_callback("energy_index", new_energy_index)
                # Calculate and notify energy delta if we have a previous value
                if old_energy_index is not None:
                    energy_delta = new_energy_index - old_energy_index
                    notify_callback("energy_delta", energy_delta)
            
            return True
            
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse energy index value: %s - %s", value, ex)
            return False
    
    def _handle_property_108(self, value: Any, notify_callback) -> bool:
        """Handle Service 5 property 108."""
        try:
            # Convert value to integer
            old_value = self._property_108_value
            
            # Update state
            self._property_108_value = int(value)
            
            # Send notification
            property_108_data = {
                PROPERTY_108_VALUE_FIELD: self._property_108_value,
            }
            notify_callback(SERVICE5_PROPERTY_108_PROPERTY_NAME, property_108_data)
            
            # Notify individual state change for backward compatibility
            if old_value != self._property_108_value:
                notify_callback("service5_property_108_value", self._property_108_value)

            return True
            
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Failed to parse Service 5 property 108 value: %s - %s", value, ex)
            return False

    # Device state properties - single source of truth
    @property
    def property_100_value(self) -> int | None:
        """Return Service 5 property 100 value."""
        return self._property_100_value

    @property
    def task_status_code(self) -> int | None:
        """Return task status code."""
        return self._task_status_code
    
    @property
    def task_status_description(self) -> str | None:
        """Return task status description."""
        if self._task_status_code is None:
            return None
        # Return mapped description or generic for unknown codes
        return TASK_STATUS_MAPPING[self._task_status_code]
    
    @property
    def property_105_value(self) -> int | None:
        """Return Service 5 property 105 value."""
        return self._property_105_value
    
    @property
    def property_106_value(self) -> int | None:
        """Return Service 5 property 106 value."""
        return self._property_106_value
    
    @property
    def energy_index(self) -> int | None:
        """Return energy/discharge index value."""
        return self._energy_index
    
    @property
    def property_108_value(self) -> int | None:
        """Return Service 5 property 108 value."""
        return self._property_108_value
    
    @property
    def has_energy_tracking(self) -> bool:
        """Return True if energy tracking is active (energy index is available)."""
        return self._energy_index is not None