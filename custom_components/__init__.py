"""The Roroshetta Sense integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: RoroshettaConfigEntry) -> bool:
    """Set up Roroshetta Sense from a config entry."""
    _LOGGER.debug("Setting up Roroshetta entry: %s", entry.entry_id)
    address = entry.unique_id
    assert address is not None
    _LOGGER.debug("Roroshetta device address: %s", address)

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if not ble_device:
        _LOGGER.error("Could not find Roroshetta device with address %s", address)
        raise ConfigEntryNotReady(
            f"Could not find Roroshetta device with address {address}"
        )

    _LOGGER.debug("Found BLE device for Roroshetta: %s", ble_device.name)
    coordinator = RoroshettaDataUpdateCoordinator(hass, _LOGGER, ble_device, entry)
    entry.runtime_data = coordinator

    entry.async_on_unload(coordinator.async_start())
    _LOGGER.debug("Started Roroshetta coordinator")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Forwarded entry setups to platforms")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoroshettaConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Roroshetta entry: %s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
