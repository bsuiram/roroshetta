"""Light platform for Roroshetta Sense."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CMD_LIGHT_BRIGHTNESS,
    CMD_LIGHT_COLOR,
    CMD_LIGHT_PRESET,
    LIGHT_MAX_KELVIN,
    LIGHT_MIN_KELVIN,
    LIGHT_PRESET_OFF,
    LIGHT_PRESET_ON,
)
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

    All three channels were confirmed against the real hood on 2026-08-28, and
    all three report back in the notify stream, so nothing here is optimistic:

    * ``CMD_LIGHT_PRESET`` switches it, and byte 53 reports on/off.
    * ``CMD_LIGHT_BRIGHTNESS`` takes 0-255, and byte 54 reports it 1:1 — the
      same range Home Assistant uses, so brightness passes straight through.
    * ``CMD_LIGHT_COLOR`` takes 0-255 warm to cool, and byte 55 reports it 1:1.
    """

    _attr_name = "Light"
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = LIGHT_MIN_KELVIN
    _attr_max_color_temp_kelvin = LIGHT_MAX_KELVIN

    def __init__(self, coordinator: RoroshettaDataUpdateCoordinator) -> None:
        """Initialise the light."""
        super().__init__(coordinator, "light")
        # Brightness and colour both read 0 while the lamp is off, so the last
        # non-zero values are kept to restore them when switching back on.
        self._last_brightness: int | None = None
        self._last_color: int | None = None

    @property
    def is_on(self) -> bool | None:
        """Whether the lamp is lit, from byte 53."""
        raw = self.coordinator.data.light_raw
        if raw is None:
            return None
        return raw > 0

    @property
    def brightness(self) -> int | None:
        """Brightness reported by the hood, byte 54."""
        if not self.is_on:
            return None
        return self.coordinator.data.light_brightness

    @property
    def color_temp_kelvin(self) -> int | None:
        """Colour reported by the hood, byte 55, mapped onto Kelvin.

        The hood has no notion of Kelvin — byte 55 is a 0-255 warm-to-cool
        slider — so this mapping exists to drive the Home Assistant UI and is
        not a measurement of the actual colour temperature.
        """
        if not self.is_on:
            return None
        raw = self.coordinator.data.light_color
        if raw is None:
            return None
        span = LIGHT_MAX_KELVIN - LIGHT_MIN_KELVIN
        return round(LIGHT_MIN_KELVIN + (raw / 255) * span)

    def _kelvin_to_raw(self, kelvin: int) -> int:
        """Map a Kelvin value back onto the hood's 0-255 colour slider."""
        span = LIGHT_MAX_KELVIN - LIGHT_MIN_KELVIN
        raw = round((kelvin - LIGHT_MIN_KELVIN) / span * 255)
        return max(0, min(255, raw))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the lamp on, then apply brightness and colour.

        Order matters, and so does restoring the remembered values: byte 54 and
        byte 55 both read 0 while the lamp is off, and the hood comes back at a
        dim default, so a bare turn-on would otherwise lose the previous
        settings.
        """
        await self.coordinator.async_send_command(CMD_LIGHT_PRESET, LIGHT_PRESET_ON)

        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_brightness)
        if brightness is not None:
            await self.coordinator.async_send_command(
                CMD_LIGHT_BRIGHTNESS, int(brightness)
            )
            self._last_brightness = int(brightness)

        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            color = self._kelvin_to_raw(int(kelvin))
        else:
            color = self._last_color
        if color is not None:
            await self.coordinator.async_send_command(CMD_LIGHT_COLOR, color)
            self._last_color = color

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the lamp off, remembering brightness and colour first.

        Brightness 0 is a dim floor rather than off, so this has to go through
        the preset command.
        """
        if self.is_on:
            data = self.coordinator.data
            if data.light_brightness:
                self._last_brightness = data.light_brightness
            if data.light_color is not None:
                self._last_color = data.light_color

        await self.coordinator.async_send_command(CMD_LIGHT_PRESET, LIGHT_PRESET_OFF)
