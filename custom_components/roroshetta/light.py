"""Light platform for Roroshetta Sense."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CMD_LIGHT_BRIGHTNESS, CMD_LIGHT_PRESET, LIGHT_PRESET_OFF, LIGHT_PRESET_ON
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator
from .entity import RoroshettaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoroshettaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the hood light."""
    async_add_entities([RoroshettaLight(entry.runtime_data)])


class RoroshettaLight(RoroshettaEntity, LightEntity):
    """The hood's lamp.

    On/off comes from ``CMD_LIGHT_PRESET`` and brightness from
    ``CMD_LIGHT_BRIGHTNESS``, both confirmed against the real hood on
    2026-08-28. Brightness takes the same 0-255 range Home Assistant uses, so it
    passes straight through.
    """

    _attr_name = "Light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: RoroshettaDataUpdateCoordinator) -> None:
        """Initialise the light."""
        super().__init__(coordinator, "light")
        # The hood reports no brightness anywhere in the payload: byte 53 holds
        # a preset index when set over BLE. So brightness is tracked optimistically
        # from what we last sent, and is None until we have sent something.
        self._brightness: int | None = None

    @property
    def is_on(self) -> bool | None:
        """Whether the lamp is lit, from byte 53.

        Non-zero covers both the preset index written over BLE and the
        brightness value the hood writes when the lamp is switched at its own
        controls.
        """
        raw = self.coordinator.data.light_raw
        if raw is None:
            return None
        return raw > 0

    @property
    def brightness(self) -> int | None:
        """Last brightness we commanded, or None if we never have."""
        return self._brightness if self.is_on else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the lamp on, then apply brightness.

        Order matters and so does the re-apply: the hood drops back to a dim
        default across an off/on cycle, so a bare turn-on would silently lose a
        previously set brightness.
        """
        await self.coordinator.async_send_command(CMD_LIGHT_PRESET, LIGHT_PRESET_ON)

        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        if brightness is not None:
            await self.coordinator.async_send_command(
                CMD_LIGHT_BRIGHTNESS, int(brightness)
            )
            self._brightness = int(brightness)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the lamp off.

        Brightness 0 is a dim floor rather than off, so this has to go through
        the preset command.
        """
        await self.coordinator.async_send_command(CMD_LIGHT_PRESET, LIGHT_PRESET_OFF)
        self.async_write_ha_state()
