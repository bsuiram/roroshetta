"""The Roroshetta Sense integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

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

    # Deliberately no availability check here. Right after a restart the
    # bluetooth cache is often still cold, and failing setup on that produced a
    # spurious error every boot. The notify loop waits for the device instead.
    coordinator = RoroshettaDataUpdateCoordinator(hass, _LOGGER, entry)
    entry.runtime_data = coordinator

    await coordinator.async_start_notify()
    _LOGGER.debug("Started Roroshetta coordinator")

    async def _async_stop_on_shutdown(_event: Event) -> None:
        """Drop the BLE link when HA shuts down.

        The notify loop parks on a connection that HA will not tear down by
        itself, which delays shutdown and logs a warning about tasks still
        running after the final writes stage.
        """
        await coordinator.async_stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, _async_stop_on_shutdown
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Forwarded entry setups to platforms")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoroshettaConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Roroshetta entry: %s", entry.entry_id)
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
