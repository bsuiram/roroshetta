"""Config flow for Roroshetta Sense."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_discovered_service_info
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, MANUFACTURER_ID, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


def _is_roroshetta(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    """Match the same devices the manifest bluetooth matchers do."""
    return (
        SERVICE_UUID in info.service_uuids
        or (info.name or "") == "Roroshetta Sense"
        or MANUFACTURER_ID in info.manufacturer_data
    )


class RoroshettaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Roroshetta Sense."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: bluetooth.BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device manually, for when discovery has not fired."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._discovery_info = self._discovered[address]
            return await self.async_step_pair()

        configured = self._async_current_ids()
        self._discovered = {
            info.address: info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.address not in configured and _is_roroshetta(info)
        }
        _LOGGER.debug(
            "Manual setup found %d unconfigured Roroshetta device(s)",
            len(self._discovered),
        )
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{info.name or 'Roroshetta Sense'} ({address})"
                            for address, info in self._discovered.items()
                        }
                    )
                }
            ),
        )

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""
        _LOGGER.debug(
            "Bluetooth discovery triggered for Roroshetta device: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        _LOGGER.debug(
            "Roroshetta device discovery info stored, proceeding to confirm step"
        )

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup."""
        assert self._discovery_info is not None
        _LOGGER.debug(
            "Confirm step called for Roroshetta device: %s",
            self._discovery_info.address,
        )

        if user_input is not None:
            _LOGGER.debug(
                "User confirmed setup for Roroshetta device: %s",
                self._discovery_info.address,
            )
            return await self.async_step_pair()

        self._set_confirm_only()
        _LOGGER.debug(
            "Showing confirm form for Roroshetta device: %s",
            self._discovery_info.address,
        )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovery_info.name or "Roroshetta Sense",
                "address": format_mac(self._discovery_info.address),
            },
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to put the device into pairing mode."""
        assert self._discovery_info is not None
        _LOGGER.debug(
            "Pairing step called for Roroshetta device: %s",
            self._discovery_info.address,
        )

        if user_input is not None:
            _LOGGER.debug(
                "User confirmed pairing mode for Roroshetta device: %s",
                self._discovery_info.address,
            )
            # Allow a short window for the device to accept pairing.
            await asyncio.sleep(5)
            return self.async_create_entry(
                title=self._discovery_info.name or "Roroshetta Sense",
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: self._discovery_info.name or "Roroshetta Sense",
                },
            )

        self._set_confirm_only()
        _LOGGER.debug(
            "Showing pairing form for Roroshetta device: %s",
            self._discovery_info.address,
        )
        return self.async_show_form(
            step_id="pair",
            description_placeholders={
                "name": self._discovery_info.name or "Roroshetta Sense",
                "address": format_mac(self._discovery_info.address),
            },
        )
