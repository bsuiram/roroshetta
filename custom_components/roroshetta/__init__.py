"""The Roroshetta Sense integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SERVICE_SEND_COMMAND
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator

PLATFORMS = [Platform.BUTTON, Platform.FAN, Platform.LIGHT, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


def _coerce_code(value: object) -> int:
    """Accept a command code as an int or as a hex string like "0x2005"."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise vol.Invalid(f"Invalid command code: {value!r}")


SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("code"): _coerce_code,
        vol.Optional("param", default=0): _coerce_code,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register domain-wide actions.

    Actions belong here rather than in ``async_setup_entry`` so they exist
    whether or not an entry happens to be loaded; the handler resolves the
    device at call time and reports clearly if there is none.
    """

    async def _async_send_command(call: ServiceCall) -> None:
        """Write one raw command to the hood's command characteristic.

        Deliberately raw rather than a friendly light/fan service: the command
        set is still being mapped, and this exists so commands can be tried on
        demand against a live connection instead of from a redeploy. See
        captures/gatt.md for what the known codes do.
        """
        entries = [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if isinstance(
                getattr(entry, "runtime_data", None), RoroshettaDataUpdateCoordinator
            )
        ]

        if device_id := call.data.get(ATTR_DEVICE_ID):
            device = dr.async_get(hass).async_get(device_id)
            if device is None:
                raise HomeAssistantError(f"Unknown device_id {device_id}")
            entries = [e for e in entries if e.entry_id in device.config_entries]

        if not entries:
            raise HomeAssistantError("No loaded Roroshetta device to send to")
        if len(entries) > 1:
            raise HomeAssistantError(
                "Several Roroshetta devices are set up; pass device_id to pick one"
            )

        await entries[0].runtime_data.async_send_command(
            call.data["code"], call.data["param"]
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _async_send_command,
        schema=SEND_COMMAND_SCHEMA,
    )
    return True


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
