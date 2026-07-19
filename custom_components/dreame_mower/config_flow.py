"""Config flow for Dreame Mower Implementation."""

from __future__ import annotations
from typing import Any
import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.device_registry import format_mac
from homeassistant.core import callback

from .dreame.cloud.cloud_base import DreameMowerCloudBase
from .const import CONF_NOTIFY, CONF_MAP_ROTATION, CONF_MAP_SHOW_TITLE, CONF_MAP_SHOW_LEGEND, CONF_MAP_PADDING, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Implementation specific constants
CONF_MODEL = "model"
CONF_SERIAL = "serial"
CONF_COUNTRY = "country"
CONF_MAC = "mac"
CONF_DID = "did"
CONF_ACCOUNT_TYPE = "account_type"
CONF_DEVICE_TYPE = "device_type"

DEVICE_TYPE_MOWER = "mower"
DEVICE_TYPE_SWBOT = "swbot"

# Account type titles
ACCOUNT_TITLE_DREAME = "Dreamehome Account"
ACCOUNT_TITLE_MOVA = "MOVAhome Account"

# Supported models
DREAME_MODELS = [
    "dreame.mower.",
    "mova.mower.",
    "dreame.swbot.",
]

model_map = {
    "dreame.mower.p2255": "DREAME A1",
    "dreame.mower.g2422": "DREAME A1 Pro", 
    "dreame.mower.g2408": "DREAME A2",
    "dreame.mower.g2541e": "DREAME A3 AWD Pro 3500",
    "mova.mower.g2405a": "MOVA 600",
    "mova.mower.g2405b": "MOVA 600 Kit",
    "mova.mower.g2405c": "MOVA 1000",
    "mova.mower.g2529b": "MOVA LiDAX 800 Ultra",
    "dreame.swbot.g2509": "Dreame Z1",
}

def _device_type_for_model(model: str) -> str:
    """Derive device type from model string."""
    if model.startswith("dreame.swbot."):
        return DEVICE_TYPE_SWBOT
    return DEVICE_TYPE_MOWER

# Notification options - focused on error, warning and info notifications
NOTIFICATION_INFORMATION = "information"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_ERROR = "error"

NOTIFICATION = {
    NOTIFICATION_INFORMATION: "Information",
    NOTIFICATION_WARNING: "Warning", 
    NOTIFICATION_ERROR: "Error",
}


class DreameMowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dreame Mower."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DreameMowerOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.account_type: str | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.country: str | None = None
        self.devices: dict[str, Any] = {}
        self.device_id: str | None = None
        self.mac: str | None = None
        self.model: str | None = None
        self.serial_number: str | None = None
        self.name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle account type selection."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("account_type", default="dreame"): vol.In({
                        "dreame": "Dreamehome",
                        "mova": "MOVAhome"
                    })
                })
            )

        account_type = user_input.get("account_type", "dreame")
        if account_type == "dreame":
            return await self.async_step_dreame()
        elif account_type == "mova":
            return await self.async_step_mova()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("account_type", default="dreame"): vol.In({
                    "dreame": "Dreamehome",
                    "mova": "MOVAhome"
                })
            }),
            errors={"base": "invalid_account_type"}
        )

    async def async_step_dreame(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure a dreame mower device through the Miio Cloud."""
        return await self._async_step_account_login("dreame", user_input, errors or {})

    async def async_step_mova(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure a mova mower device through the Miio Cloud."""
        return await self._async_step_account_login("mova", user_input, errors or {})

    async def _async_step_account_login(
        self,
        account_type: str,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Common logic for configuring dreame or mova mower devices through the Miio Cloud."""
        if errors is None:
            errors = {}
            
        if user_input is not None:
            self.account_type = account_type
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            country = user_input.get(CONF_COUNTRY)

            if username and password and country:
                self.username = username
                self.password = password
                self.country = country

                try:
                    # Use lightweight auth class for device discovery
                    auth = DreameMowerCloudBase(
                        username=self.username,
                        password=self.password,
                        country=self.country,
                        account_type=account_type,
                    )
                    await self.hass.async_add_executor_job(auth.connect)

                    if not auth.connected:
                        _LOGGER.warning(
                            "Login failed for account_type=%s, country=%s, username=%s",
                            account_type,
                            self.country,
                            self.username,
                        )
                        errors["base"] = "login_error"
                    else:
                        devices = await self.hass.async_add_executor_job(
                            auth.get_devices
                        )
                        if devices:
                            found = list(
                                filter(
                                    lambda d: any(
                                        str(d["model"]).startswith(prefix)
                                        for prefix in DREAME_MODELS
                                    ),
                                    devices["page"]["records"],
                                )
                            )

                            self.devices = {}
                            for device in found:
                                name = (
                                    device["customName"]
                                    if device["customName"]
                                    and len(device["customName"]) > 0
                                    else device["deviceInfo"]["displayName"]
                                )
                                # Use more informative device name formatting
                                model = model_map.get(device["model"], device["model"])
                                modelId = device["model"]
                                list_name = f"{name} - {model} ({modelId})"
                                self.devices[list_name] = device

                            if self.devices:
                                if len(self.devices) == 1:
                                    self._extract_info(list(self.devices.values())[0])
                                    return await self.async_step_connect()
                                return await self.async_step_devices()

                        errors["base"] = "no_devices"
                except AbortFlow:
                    raise
                except Exception as ex:
                    _LOGGER.exception("Error connecting to cloud service: %s", ex)
                    errors["base"] = "cannot_connect"
            else:
                errors["base"] = "credentials_incomplete"

        return self.async_show_form(
            step_id=account_type,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.username or ""): str,
                    vol.Required(CONF_PASSWORD, default=self.password or ""): str,
                    vol.Required(CONF_COUNTRY, default=self.country or "eu"): vol.In(
                        ["cn", "eu", "us", "ru", "sg"]
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle multiple Dreame/Mova Mower devices found."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._extract_info(self.devices[user_input["devices"]])
            return await self.async_step_connect()

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {vol.Required("devices"): vol.In(list(self.devices))}
            ),
            errors=errors,
        )

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect to a Dreame/Mova Mower device."""
        errors: dict[str, str] = {}
        try:
            if not self.username or not self.password:
                raise ValueError("Username and password are required")
            if not self.country or not self.account_type:
                raise ValueError("Country and account type are required")
            if not self.device_id:
                raise ValueError("Device ID is required for connection")

            # Test connection using cloud base
            auth = DreameMowerCloudBase(
                username=self.username,
                password=self.password,
                country=self.country,
                account_type=self.account_type,
            )
            await self.hass.async_add_executor_job(auth.connect)
            
            if not auth.connected:
                raise ConnectionError("Failed to connect to cloud service")
                
        except Exception as ex:
            _LOGGER.exception("Cannot connect to device: %s", ex)
            errors["base"] = "cannot_connect"

        if not errors:
            if self.mac:
                await self.async_set_unique_id(format_mac(self.mac))
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_MAC: self.mac,
                        CONF_DID: self.device_id,
                    }
                )

            if self.model and any(self.model.startswith(prefix) for prefix in DREAME_MODELS):
                if self.name is None:
                    self.name = self.model
                return await self.async_step_options()
            else:
                errors["base"] = "unsupported"

        # If we get here, there was an error - redirect back to the appropriate auth step
        if self.account_type == "mova":
            return await self.async_step_mova(errors=errors)
        else:
            return await self.async_step_dreame(errors=errors)

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Dreame/Mova Mower options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.name = user_input[CONF_NAME]

            # Determine config entry title based on selected account type
            if self.account_type == "dreame":
                entry_title = ACCOUNT_TITLE_DREAME
            elif self.account_type == "mova":
                entry_title = ACCOUNT_TITLE_MOVA
            else:
                # Fallback: keep using the device name if an unexpected type appears
                entry_title = self.name

            assert self.model is not None
            return self.async_create_entry(
                title=entry_title,
                data={
                    CONF_NAME: self.name,
                    CONF_USERNAME: self.username,
                    CONF_PASSWORD: self.password,
                    CONF_COUNTRY: self.country,
                    CONF_MAC: self.mac,
                    CONF_DID: self.device_id,
                    CONF_MODEL: self.model,
                    CONF_SERIAL: self.serial_number,
                    CONF_ACCOUNT_TYPE: self.account_type,
                    CONF_DEVICE_TYPE: _device_type_for_model(self.model),
                },
                options={
                    CONF_NOTIFY: user_input[CONF_NOTIFY],
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=self.name): str,
                    vol.Required(CONF_NOTIFY, default=list(NOTIFICATION)): cv.multi_select(NOTIFICATION),
                }
            ),
            errors=errors,
        )

    def _extract_info(self, device_info: dict[str, Any]) -> None:
        """Extract device information from the API response."""
        self.device_id = device_info.get("did")
        self.mac = device_info.get("mac")  # MAC is directly in device_info, not nested
        self.model = device_info.get("model")
        self.serial_number = device_info.get("sn", "")  # Serial number never changes
        
        # Extract device name
        self.name = (
            device_info["customName"]
            if device_info.get("customName") and len(device_info["customName"]) > 0
            else device_info.get("deviceInfo", {}).get("displayName", self.model)
        )

class DreameMowerOptionsFlow(OptionsFlow):
    """Handle options flow for Dreame Mower."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_notify = self.config_entry.options.get(CONF_NOTIFY)
        # Filter out any invalid notification types
        if current_notify:
            current_notify = [n for n in current_notify if n in NOTIFICATION]
        current_rotation = self.config_entry.options.get(CONF_MAP_ROTATION, 0)
        current_show_title = self.config_entry.options.get(CONF_MAP_SHOW_TITLE, True)
        current_show_legend = self.config_entry.options.get(CONF_MAP_SHOW_LEGEND, True)
        current_padding = self.config_entry.options.get(CONF_MAP_PADDING, 50)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_NOTIFY, default=current_notify): cv.multi_select(NOTIFICATION),
                vol.Required(CONF_MAP_ROTATION, default=current_rotation): vol.All(vol.Coerce(int), vol.In([0, 90, 180, 270])),
                vol.Required(CONF_MAP_SHOW_TITLE, default=current_show_title): bool,
                vol.Required(CONF_MAP_SHOW_LEGEND, default=current_show_legend): bool,
                vol.Required(CONF_MAP_PADDING, default=current_padding): vol.All(int, vol.Range(min=0, max=200)),
            }),
        )